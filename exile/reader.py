"""Independent, bounded, read-only reader for explicitly validated profiles.

No upstream assemblies are loaded. All patch-dependent offsets come from JSON.
Only the capabilities verified for the matching build are exposed.
"""
from __future__ import annotations

import math
import re
import struct
import time

from exile.model import Snapshot
from exile.terrain import decode_height_tiles, terrain_grid_point, walkable_regions
from exile.radar import classify_object,classify_actor,preferred_object_name
from exile.areas import town_or_hideout
from exile.projection import project


def usable_vital(total: int, reserved_flat: int, reserved_percent: int) -> int:
    if not 0 <= total <= 100_000_000 or not 0 <= reserved_flat <= total or not 0 <= reserved_percent <= 10000:
        raise ValueError("Invalid vital reservation fields")
    return max(0, total - reserved_flat - math.ceil(total * reserved_percent / 10000))


def unpack_terrain(raw: bytes, width: int, height: int, stride: int) -> list[bytes]:
    if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 32_000_000 or stride != (width + 1) // 2:
        raise ValueError("Unsupported terrain dimensions")
    if len(raw) != stride * height:
        raise ValueError("Terrain buffer length does not match dimensions")
    rows = []
    for y in range(height):
        packed = raw[y * stride:(y + 1) * stride]
        row = bytes(nibble for value in packed for nibble in (value & 15, value >> 4))[:width]
        if any(value > 5 for value in row):
            raise ValueError("Unknown terrain collision values")
        rows.append(row)
    return rows


def contained_rect(rect, panel, viewport):
    x, y, width, height = rect
    px, py, pw, ph = panel
    return (all(math.isfinite(v) for v in (*rect, *panel)) and width > 1 and height > 1 and
            max(0, px) - .5 <= x and max(0, py) - .5 <= y and
            x + width <= min(viewport[0], px + pw) + .5 and
            y + height <= min(viewport[1], py + ph) + .5)


class Reader:
    def __init__(self, profile):
        self.profile = profile
        self.o = profile["offsets"]
        self.base = 0
        self.pid = 0
        self.names = {}
        self.paths = {}
        self.grid_key = None
        self.grid = []
        self.grid_regions = None
        self.height_key = None
        self.height_grid = None
        self.landmarks_key = None
        self.landmarks = []
        self.entity_cache = {}
        self.scene_epoch = None
        self.scene_addresses_cache = []
        self.scene_scan_at = 0
        self.scene_identities = {}
        self.display_names = {}
        self.object_availability = {}
        self.preload_key = None
        self.preload_objects = []
        self.preload_index = 0
        self.preload_names = set()
        self.preload_next_scan = 0
        self.inventory_at = 0
        self.inventory_items = []
        self.inventory_tabs = []
        self.carried_at=0
        self.carried_epoch=None
        self.carried=[]
        self.item_panels=[]

    def q(self, address):
        return struct.unpack("<Q", self.memory.read(address, 8))[0]

    def integer(self, address):
        return struct.unpack("<i", self.memory.read(address, 4))[0]

    def ascii(self, address, limit=96):
        return self.memory.read(address, limit).split(bytes([0]), 1)[0].decode("ascii")

    def utf16(self, address, length=None, maximum=256, multiline=False):
        if length is not None and not 0 < length <= maximum:
            raise ValueError("Invalid game string length")
        raw = self.memory.read(address, 2 * (length if length is not None else maximum))
        stop = next((i for i in range(0, len(raw), 2) if raw[i:i + 2] == bytes([0, 0])), len(raw))
        text = raw[:stop].decode("utf-16-le")
        if any(ord(c) < 32 and not(multiline and c in '\n\r\t')for c in text):
            raise ValueError("Invalid game string characters")
        return text

    def vector(self, address, stride=8, limit=256):
        start, end, capacity = struct.unpack("<QQQ", self.memory.read(address, 24))
        if not start <= end <= capacity or (end - start) % stride or (end - start) // stride > limit:
            raise ValueError("Invalid game vector")
        if start == end:
            return b""
        return self.memory.read(start, end - start)

    def monster_boss(self, component, owner):
        """Require an explicit map-boss modifier; rarity never establishes it."""
        vectors=self.o.get('monster_mod_vectors')
        accepted=set(self.profile.get('map_boss_modifiers',[]))
        if not vectors or not accepted:return None
        size=self.o['monster_mod_record_size']
        definition_offset=self.o['monster_mod_definition']
        if not 8<=size<=256 or not 0<=definition_offset<=size-8:
            raise ValueError('Invalid monster modifier layout')
        header=self.owned_component(component,owner,max(vectors)+24)
        found=False
        for offset in vectors:
            expected=header[offset:offset+24]
            raw=self.vector(component+offset,stride=size,limit=256)
            for index in range(0,len(raw),size):
                definition=struct.unpack_from('<Q',raw,index+definition_offset)[0]
                if not definition:raise ValueError('Missing monster modifier definition')
                name=self.utf16(self.q(definition+self.o['monster_mod_id']),maximum=128)
                if not re.fullmatch(r'[A-Za-z0-9_]+',name):
                    raise ValueError('Invalid monster modifier identifier')
                if name in accepted:found=True
            if self.memory.read(component+offset,24)!=expected:
                raise ValueError('Monster modifiers changed during read')
        # Revalidate ownership after following the modifier definitions.
        self.owned_component(component,owner,16)
        return found

    def component_name(self, vtable):
        if vtable in self.names:
            return self.names[vtable]
        if not self.base <= vtable < self.base + self.o["image_size"]:
            raise ValueError("Component vtable is outside the executable")
        function = self.q(vtable + self.o["component_name_vslot"] * 8)
        code = self.memory.read(function, 8)
        if code[:3] != bytes.fromhex("48 8d 05") or code[7] != 0xc3:
            raise ValueError("Component name getter has changed")
        target = function + 7 + struct.unpack_from("<i", code, 3)[0]
        if not self.base <= target < self.base + self.o["image_size"]:
            raise ValueError("Component name is outside the executable")
        name = self.ascii(target)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name):
            raise ValueError("Invalid component type name")
        self.names[vtable] = name
        return name

    def components(self, entity, item=False, raw=None):
        if raw is None:
            raw = self.vector(entity + self.o["entity_components"], limit=128)
        result = {}
        for offset in range(0, len(raw), 8):
            pointer = struct.unpack_from("<Q", raw, offset)[0]
            if not pointer:
                continue
            vtable, owner = struct.unpack("<QQ", self.memory.read(pointer, 16))
            if owner != entity:
                raise ValueError("Component owner mismatch")
            if item:
                name = self.profile.get("item_component_vtables", {}).get(hex(vtable - self.base))
                if name is None:
                    continue
            else:
                name = self.component_name(vtable)
            if name in result:
                raise ValueError("Duplicate component type")
            result[name] = pointer
        return result

    def native_string(self, address, maximum=256, multiline=False):
        raw = self.memory.read(address, 32)
        length, capacity = struct.unpack_from("<QQ", raw, 16)
        if not 0 <= length <= maximum or capacity < length:
            raise ValueError("Invalid native string size")
        if length == 0:
            return ""
        pointer = struct.unpack_from("<Q", raw)[0] if capacity > 7 else address
        return self.utf16(pointer, length, maximum,multiline=multiline)

    def preloads(self, counter):
        if "file_root_rva" not in self.o:
            return []
        root = self.q(self.base + self.o["file_root_rva"])
        key = (root, counter)
        now = time.monotonic()
        if self.preload_key != key or (self.preload_index >= len(self.preload_objects) and now >= self.preload_next_scan):
            objects = []
            for shard in range(self.o["file_shards"]):
                raw = self.vector(root + shard * self.o["file_shard_size"], stride=24, limit=20000)
                objects.extend(struct.unpack_from("<Q", raw, i + 16)[0] for i in range(0, len(raw), 24))
            if len(objects) > 200000:
                raise ValueError("File registry exceeds limit")
            if self.preload_key != key:
                self.preload_names.clear()
            self.preload_key, self.preload_objects, self.preload_index = key, objects, 0
            self.preload_next_scan = now + 10
        end = min(len(self.preload_objects), self.preload_index + 1500)
        for obj in self.preload_objects[self.preload_index:end]:
            if not obj:
                continue
            try:
                record = self.memory.read(obj, 0x50)
                generation = struct.unpack_from("<I", record, self.o["file_area_counter"])[0]
                if generation != counter:
                    continue
                pointer = struct.unpack_from("<Q", record, self.o["file_name"])[0]
                length = struct.unpack_from("<Q", record, self.o["file_name_length"])[0]
                name = self.utf16(pointer, length, maximum=1024).split("@", 1)[0]
                if "/" in name:
                    self.preload_names.add(name)
            except (OSError, ValueError, UnicodeError):
                continue
        self.preload_index = end
        return sorted(self.preload_names)

    def inventory_holders(self, server, offset):
        raw = self.vector(server + offset, stride=24, limit=4096)
        return [(struct.unpack_from("<I", raw, i)[0], struct.unpack_from("<Q", raw, i + 8)[0])
                for i in range(0, len(raw), 24)]

    def inventory_slots(self, inventory):
        columns, rows = struct.unpack("<ii", self.memory.read(inventory + self.o["inventory_dimensions"], 8))
        if not 0 < columns <= 2048 or not 0 < rows <= 2048 or columns * rows > 200000:
            raise ValueError("Invalid inventory dimensions")
        count = self.integer(inventory + self.o["inventory_item_count"])
        if not 0 <= count <= 10000:
            raise ValueError("Invalid inventory item count")
        if not count:
            return []
        grid = self.q(inventory + self.o["inventory_grid"])
        pointers = self.memory.read(grid, columns * rows * 8)
        unique = {struct.unpack_from("<Q", pointers, i)[0] for i in range(0, len(pointers), 8)} - {0}
        if len(unique) > count + 8:
            raise ValueError("Inventory changed while reading")
        result = []
        for slot in unique:
            raw = self.memory.read(slot, 24)
            entity = struct.unpack_from("<Q", raw)[0]
            x, y, right, bottom = struct.unpack_from("<iiii", raw, 8)
            if not 0 <= x < right <= columns or not 0 <= y < bottom <= rows:
                continue
            result.append((entity, x, y, right - x, bottom - y))
        return result

    def item_variant(self,component,owner):
        keys=('item_explicit_mods','item_mod_size','item_mod_definition','item_mod_id')
        if not all(key in self.o for key in keys):return None,[]
        offset,size,definition,id_offset=(self.o[key]for key in keys)
        if not 0<=offset<=2048 or not 8<=size<=256 or not 0<=definition<=size-8:return None,[]
        header=self.owned_component(component,owner,offset+24)
        raw=self.vector(component+offset,stride=size,limit=32)
        if not raw:return None,[]
        identifiers=[]
        for index in range(0,len(raw),size):
            pointer=struct.unpack_from('<Q',raw,index+definition)[0]
            identifier=self.utf16(self.q(pointer+id_offset))
            if not re.fullmatch(r'[A-Za-z0-9_]+',identifier):raise ValueError('Invalid item modifier ID')
            identifiers.append(identifier)
        if self.memory.read(component+offset,24)!=header[offset:offset+24]:raise ValueError('Item modifiers changed')
        self.owned_component(component,owner,16)
        return any(identifier.startswith('MutatedUnique')for identifier in identifiers),identifiers

    def inventory_modifier_records(self,component,owner):
        """Read bounded native modifier identifiers and roll vectors for inventory gear."""
        keys=('item_explicit_mods','item_implicit_mods','item_mod_size','item_mod_definition','item_mod_values','item_mod_id')
        if not all(key in self.o for key in keys):return None
        offset=self.o['item_explicit_mods'];implicit=self.o['item_implicit_mods'];size=self.o['item_mod_size'];definition=self.o['item_mod_definition'];values_offset=self.o['item_mod_values']
        if not 24<=size<=256 or not 0<=definition<=size-8 or not 0<=values_offset<=size-24:return None
        if not 0<=implicit<=2048 or not 0<=offset<=2048:return None
        header=self.owned_component(component,owner,max(offset,implicit)+24)
        result=[];observed=[]
        for section,where in (('implicit',implicit),('explicit',offset)):
            raw=self.vector(component+where,stride=size,limit=16)
            for index in range(0,len(raw),size):
                start,end,capacity=struct.unpack_from('<QQQ',raw,index+values_offset)
                if not start<=end<=capacity or (end-start)%4 or not 1<=(end-start)//4<=4:raise ValueError('Invalid modifier rolls')
                value_bytes=self.memory.read(start,end-start)
                values=list(struct.unpack('<'+'i'*((end-start)//4),value_bytes));observed.append((start,value_bytes))
                pointer=struct.unpack_from('<Q',raw,index+definition)[0]
                identifier=self.utf16(self.q(pointer+self.o['item_mod_id']))
                if not re.fullmatch(r'[A-Za-z0-9_]+',identifier):raise ValueError('Invalid modifier identifier')
                result.append(dict(id=identifier,values=values,section=section))
            if self.memory.read(component+where,24)!=header[where:where+24]:raise ValueError('Modifier vector changed')
        if any(self.memory.read(start,len(value))!=value for start,value in observed):raise ValueError('Modifier rolls changed')
        self.owned_component(component,owner,16)
        return result

    def item_summary(self, entity, assessment=False):
        metadata = self.path(entity)
        if not metadata.startswith("Metadata/Items/"):
            raise ValueError("Inventory entry is not an item")
        components = self.components(entity, item=True)
        if "Base" not in components:
            raise ValueError("Item base component has not been verified")
        definition = self.q(components["Base"] + self.o["item_base_definition"])
        base_name = self.native_string(definition + self.o["item_base_name"])
        if not base_name:
            raise ValueError("Item base name is missing")
        name, rarity = base_name, 0
        if "Mods" in components:
            mods = components["Mods"]
            rarity = self.integer(mods + self.o["item_rarity"])
            if rarity not in range(4):
                raise ValueError("Unknown item rarity")
            if rarity in (2, 3):
                words = self.vector(mods + self.o["item_name_words"], stride=16, limit=8)
                pieces = []
                for offset in range(0, len(words), 16):
                    word = struct.unpack_from("<Q", words, offset)[0]
                    pieces.append(self.utf16(self.q(word + self.o["item_word_text"])))
                if pieces:
                    name = " ".join(pieces)
        links = 0
        groups = b''
        if "Sockets" in components:
            groups = self.vector(components["Sockets"] + self.o["socket_links"], stride=1, limit=6)
            if any(not 1 <= value <= 6 for value in groups) or sum(groups) > 6:
                raise ValueError("Invalid socket link groups")
            links = max(groups, default=0)
        quantity = 1
        if "Stack" in components:
            quantity = self.integer(components["Stack"] + self.o["item_stack_size"])
            if not 1 <= quantity <= 1_000_000_000:
                raise ValueError("Invalid stack quantity")
        foulborn=None;variant_mods=[];identified=None
        if rarity in (2,3) and 'Mods' in components:
            try:
                if rarity==3:foulborn,variant_mods=self.item_variant(components['Mods'],entity)
                if 'item_identified'in self.o:
                    flag=self.memory.read(components['Mods']+self.o['item_identified'],1)[0]
                    if flag in (0,1):identified=bool(flag)
            except (OSError,ValueError,UnicodeError):pass
        visual_identity=''
        if rarity==3 and 'item_visual_identity' in self.o and 'visual_identity_id' in self.o:
            try:
                component=components['Base'];offset=self.o['item_visual_identity']
                owned=self.owned_component(component,entity,offset+8)
                identity=struct.unpack_from('<Q',owned,offset)[0]
                value=self.utf16(self.q(identity+self.o['visual_identity_id']))
                if re.fullmatch(r'[A-Za-z0-9_]{1,128}',value):visual_identity=value
            except (OSError,ValueError,UnicodeError):pass
        art='' 
        if 'RenderItem' in components and 'item_render_resource' in self.o:
            try:
                component=components['RenderItem'];offset=self.o['item_render_resource']
                owned=self.owned_component(component,entity,offset+8)
                resource=self.utf16(struct.unpack_from('<Q',owned,offset)[0])
                if re.fullmatch(r'Art/2DItems/[A-Za-z0-9_ /.-]+\.dds',resource):art=resource
            except (OSError,ValueError,UnicodeError):pass
        assessment_mods=None
        if assessment and rarity==2 and identified is True and 'Mods' in components:
            from exile.items import equipment_metadata
            if equipment_metadata(metadata):
                try:
                    assessment_mods=self.inventory_modifier_records(components['Mods'],entity)
                except (OSError,ValueError,UnicodeError,struct.error):pass
        result={"assessment_mods":assessment_mods,"visual_identity":visual_identity,"foulborn":foulborn,"variant_mods":variant_mods,"identified":identified,"art": art,"entity": entity, "name": name, "base": base_name, "metadata": metadata,
                "rarity": rarity, "links": links, "quantity": quantity,
                "sockets": sum(groups),
                "stackable": 'Stack' in components,
                "corrupted": None, "mods": [], "visible": False, "components": components}
        if assessment_mods:
            from exile.rare_inventory import rating_for_item
            result['inventory_rating']=rating_for_item(result,getattr(self,'assessment_archetype','General'))
        return result

    def carried_items(self,session,epoch,assessment=True):
        now=time.monotonic()
        cache_key=(epoch,assessment,getattr(self,'assessment_archetype','General'))
        if self.carried_epoch==cache_key and now-self.carried_at<.5:return self.carried
        server=self.q(session+self.o['server_data']);items=[];loaded=False
        allowed=set(self.o['main_inventory_slots'])
        for identifier,inventory in self.inventory_holders(server,self.o['personal_inventories']):
            native=self.memory.read(inventory+self.o['inventory_type'],8)
            slot=native[self.o['inventory_slot_delta']]
            if native[0]!=self.o['main_inventory_type'] or slot not in allowed:continue
            if slot==self.o['main_inventory_slots'][0]:loaded=True
            for entity,x,y,width,height in self.inventory_slots(inventory):
                try:
                    item=self.item_summary(entity,assessment=assessment);item.pop('components',None)
                except (OSError,ValueError,UnicodeError) as exc:
                    item=dict(entity=entity,name='Unread item',base='',quantity=None,rarity=None,
                              metadata='',links=0,corrupted=None,decode_error=str(exc),visible=False)
                item.update(scope='inventory',inventory_slot=slot,x=x,y=y,width=width,height=height)
                items.append(item)
        self.carried,self.carried_at,self.carried_epoch=items,now,cache_key
        self.carried_loaded=loaded
        return items

    def ground_labels(self,state,viewport):
        ui=self.q(state+self.o['state_ui']);root=self.q(ui+self.o['ui_ground_labels'])
        if not root:return []
        head=self.q(root+self.o['ground_label_head'])
        if not head:return []
        node=self.q(head);seen=set();items=[]
        while node and node!=head:
            if node in seen or len(seen)>=2048:raise ValueError('Invalid ground label list')
            seen.add(node)
            raw=self.memory.read(node,40)
            next_node=struct.unpack_from('<Q',raw,self.o['ground_label_next'])[0]
            world=struct.unpack_from('<Q',raw,self.o['ground_label_world'])[0]
            label=struct.unpack_from('<Q',raw,self.o['ground_label_element'])[0]
            try:
                rect=self.element_rect(label,viewport) if label else None
                if rect and contained_rect(rect,(0,0,*viewport),viewport):
                    components=self.components(world)
                    if 'WorldItem' in components:
                        component=components['WorldItem']
                        owned=self.owned_component(component,world,self.o['world_item_entity']+8)
                        entity=struct.unpack_from('<Q',owned,self.o['world_item_entity'])[0]
                        item=self.item_summary(entity);item.pop('components',None)
                        # A disappearing label must never remain attached to its
                        # former item after pickup or loot-filter changes.
                        if self.q(node+self.o['ground_label_world'])==world and self.q(node+self.o['ground_label_element'])==label:
                            item.update(scope='ground',visible=True,rect=rect,screen=rect[:2])
                            items.append(item)
            except (OSError,ValueError,UnicodeError):pass
            node=next_node
        if self.q(ui+self.o['ui_ground_labels'])!=root or self.q(root+self.o['ground_label_head'])!=head:
            raise ValueError('Ground label root changed during read')
        return items

    def inventories(self, session, epoch):
        if "server_data" not in self.o:
            return [], []
        now = time.monotonic()
        if getattr(self, "inventory_epoch", None) == epoch and now - self.inventory_at < 2:
            return self.inventory_items, self.inventory_tabs
        server = self.q(session + self.o["server_data"])
        items, tabs = [], []
        for scope, tab_offset, inventory_offset in (
            ("personal", self.o["personal_tabs"], self.o["personal_inventories"]),
            ("guild", self.o["guild_tabs"], self.o["guild_inventories"]),
        ):
            try:
                raw = self.vector(server + tab_offset, stride=self.o["stash_tab_size"], limit=4096)
                start = self.q(server + tab_offset)
                names = [self.native_string(start + index + self.o["stash_tab_name"])
                         for index in range(0, len(raw), self.o["stash_tab_size"])]
                tab_ids = {struct.unpack_from('<I', raw, index + self.o['stash_tab_inventory_id'])[0]: index // self.o['stash_tab_size']
                           for index in range(0, len(raw), self.o['stash_tab_size'])
                           if struct.unpack_from('<I', raw, index + self.o['stash_tab_inventory_id'])[0] != 0}
                loaded = set()
                for identifier, inventory in self.inventory_holders(server, inventory_offset):
                    native = self.memory.read(inventory + self.o["inventory_type"], 8)
                    if native[self.o["inventory_slot_delta"]] != self.o["stash_inventory_slot"]:
                        continue
                    index = tab_ids.get(identifier)
                    if index is None and scope == 'guild' and identifier < len(names):
                        index = identifier
                    if index is None:continue
                    loaded.add(index)
                    for entity, x, y, width, height in self.inventory_slots(inventory):
                        try:
                            item = self.item_summary(entity)
                            item.pop("components", None)
                            item.update(scope=scope, tab=names[index], tab_index=index, x=x, y=y, width=width, height=height,
                                        inventory_type=native[0])
                            items.append(item)
                        except (OSError, ValueError, UnicodeError) as exc:
                            try:
                                metadata = self.path(entity)
                                if metadata.startswith('Metadata/Items/'):
                                    items.append(dict(entity=entity, name=metadata.rsplit('/', 1)[-1],
                                        base='Unread item details', metadata=metadata,rarity=None,links=0,quantity=None,
                                        corrupted=None,mods=[],visible=False,decode_error=str(exc),scope=scope,
                                        tab=names[index],tab_index=index,x=x,y=y,width=width,height=height,inventory_type=native[0]))
                            except (OSError, ValueError, UnicodeError):pass
                tabs.extend({"scope": scope, "index": index, "name": name, "loaded": index in loaded}
                            for index, name in enumerate(names))
            except (OSError, ValueError, UnicodeError):continue
        self.inventory_items, self.inventory_tabs = items, tabs
        self.inventory_at, self.inventory_epoch = now, epoch
        return items, tabs

    def element_rect(self, element, viewport):
        """Read layout and visibility only; never read input text."""
        chain, seen = [], set()
        while element:
            if element in seen or len(chain) >= 32:
                raise ValueError("Invalid UI parent chain")
            seen.add(element)
            headers=getattr(self,'ui_layout_headers',None)
            raw=headers.get(element)if headers is not None else None
            if raw is None:
                raw=self.memory.read(element,self.o['ui_size'])
                if headers is not None and len(headers)<20000:headers[element]=raw
            if not raw[self.o["ui_visibility"]] & self.o["ui_visible_mask"]:
                return None
            x, y = struct.unpack_from("<ff", raw, self.o["ui_position"])
            scale = struct.unpack_from("<f", raw, self.o["ui_scale"])[0]
            width, height = struct.unpack_from("<ff", raw, self.o["ui_dimensions"])
            if not all(math.isfinite(v) for v in (x, y, scale, width, height)) or not .001 <= scale <= 100:
                raise ValueError("Invalid UI layout")
            chain.append((x, y, scale, width, height))
            element = struct.unpack_from("<Q", raw, self.o["ui_parent"])[0]
        if not chain:
            return None
        root_scale = chain[-1][2]
        factor = viewport[1] / 1600 / root_scale
        x = sum(row[0] * row[2] for row in chain) * factor
        y = sum(row[1] * row[2] for row in chain) * factor
        width, height = chain[0][3] * chain[0][2] * factor, chain[0][4] * chain[0][2] * factor
        return (x, y, width, height)

    def stash_layout(self, state, items, viewport):
        ui = self.q(state + self.o["state_ui"])
        by_entity = {item["entity"]: item for item in items}
        for item in items:
            item["visible"] = False
            item.pop("screen", None)
        self.item_panels=[]
        panels=[('personal','ui_stash'),('guild','ui_guild_stash')]
        if 'ui_inventory' in self.o and getattr(self,'read_item_overlays',False):panels.append(('inventory','ui_inventory'))
        for scope, offset in panels:
            panel = self.q(ui + self.o[offset])
            panel_rect = self.element_rect(panel, viewport) if panel else None
            if panel_rect is None:
                continue
            self.item_panels.append(dict(scope=scope,rect=panel_rect))
            pending, seen = [panel], set()
            while pending:
                element = pending.pop()
                if element in seen:
                    continue
                if len(seen) >= 12000:
                    raise ValueError("Stash UI exceeds traversal limit")
                seen.add(element)
                try:
                    rect = self.element_rect(element, viewport)
                    if rect is None:
                        continue
                    entity = self.q(element + self.o["ui_item"])
                    item = by_entity.get(entity)
                    if item and item["scope"] == scope:
                        # Currency tabs use a logical item X that is unrelated to
                        # the actual slot location. Their parent is the slot box.
                        anchor = self.q(element + self.o["ui_parent"]) if item.get("inventory_type") == self.o["currency_inventory_type"] else element
                        item_rect = self.element_rect(anchor, viewport)
                        if item_rect and contained_rect(item_rect, panel_rect, viewport):
                            item.update(visible=True, screen=item_rect[:2], rect=item_rect)
                    children = self.vector(element + self.o["ui_children"], limit=4096)
                    pending.extend(struct.unpack_from("<Q", children, i)[0] for i in range(0, len(children), 8))
                except (OSError, ValueError):
                    continue

    def hovered_item(self,state,viewport):
        """Read only an item-owned tooltip, never general hover/chat text."""
        if 'state_item_hover'not in self.o:return None
        hover=self.q(state+self.o['state_item_hover'])
        if not hover:return None
        entity=self.q(hover+self.o['ui_item'])
        if not entity:return None
        item=self.item_summary(entity)
        if item['rarity']!=2 and not getattr(self,'read_all_hover',False):return None
        from exile.items import equipment_metadata
        supported=item['rarity']==2 and equipment_metadata(item.get('metadata',''))
        if not supported and not getattr(self,'read_all_hover',False):return dict(item,assessment_supported=False)
        holder=self.q(hover+self.o['ui_tooltip_holder'])
        root=self.q(holder)if holder else 0
        rect=self.element_rect(root,viewport)if root else None
        if rect is None:return None
        rows=[];pending=[(root,0)];seen=set()
        while pending:
            node,depth=pending.pop()
            if node in seen:continue
            if len(seen)>=256 or depth>16:raise ValueError('Item tooltip exceeds traversal limit')
            seen.add(node)
            # Nodes within this one item's tooltip may hold hidden advanced
            # affix descriptions. These give tiers without pressing Alt.
            text=''
            try:
                text=self.native_string(node+self.o['ui_text_plain'],maximum=2048,multiline=True)
                if text:rows.append(text)
            except (OSError,ValueError,UnicodeError):pass
            if not text and 'ui_text_styled'in self.o:
                try:
                    text=self.native_string(node+self.o['ui_text_styled'],maximum=2048,multiline=True)
                    if text:
                        import re
                        while re.search(r'<[^>]+>\{([^{}]*)\}',text):
                            text=re.sub(r'<[^>]+>\{([^{}]*)\}',r'\1',text)
                        if text:rows.append(text)
                except (OSError,ValueError,UnicodeError):pass
            try:
                children=self.vector(node+self.o['ui_children'],limit=256)
                pending.extend((struct.unpack_from('<Q',children,i)[0],depth+1)for i in range(len(children)-8,-1,-8))
            except (OSError,ValueError,UnicodeError):continue
        if self.q(state+self.o['state_item_hover'])!=hover or self.q(hover+self.o['ui_item'])!=entity or self.q(holder)!=root:
            return None
        item.pop('components',None)
        item.update(tooltip_rect=rect,tooltip_rows=rows,assessment_supported=supported,hover_captured_at=time.monotonic())
        return item

    def native_map(self, state, player, viewport):
        if 'ui_map' not in self.o:
            return None
        ui = self.q(state + self.o['state_ui'])
        root = self.q(ui + self.o['ui_map'])
        for mode, field in (('large', 'map_large'), ('small', 'map_small')):
            element = self.q(root + self.o[field])
            rect = self.element_rect(element, viewport) if element else None
            if rect is None:
                continue
            pan_x, pan_y, offset_x, offset_y = struct.unpack('<4f', self.memory.read(element + self.o['map_pan'], 16))
            zoom = struct.unpack('<f', self.memory.read(element + self.o['map_zoom'], 4))[0]
            scale = struct.unpack('<f', self.memory.read(element + self.o['ui_scale'], 4))[0]
            if not all(math.isfinite(v) for v in (pan_x, pan_y, offset_x, offset_y, zoom, scale)) or not .01 <= zoom <= 10:
                raise ValueError('Invalid native map transform')
            center = (rect[0] + pan_x + offset_x, rect[1] + pan_y + offset_y)
            if mode == 'small':
                center = (center[0] + rect[2] / 2, center[1] + rect[3] / 2)
            clip = rect if mode == 'small' else (0, 0, *viewport)
            return dict(mode=mode, center=center, player=player, clip=clip,
                        basis_x=self.o['map_basis_x'] * scale * zoom,
                        basis_y=self.o['map_basis_y'] * scale * zoom)
        return None

    def path(self, entity):
        definition = self.q(entity + self.o["entity_definition"])
        pointer = self.q(definition + self.o["definition_path"])
        length = self.q(definition + self.o["definition_path_length"])
        key = (definition, pointer, length)
        if key not in self.paths:
            name = self.utf16(pointer, length, maximum=512)
            if not name.startswith("Metadata/"):
                raise ValueError("Entity metadata is invalid")
            if len(self.paths) > 20000:
                self.paths.clear()
            self.paths[key] = name
        return self.paths[key]

    def life(self, component, mana=False):
        origin = component + self.o["mana_vital" if mana else "life_vital"]
        raw = self.memory.read(origin, 0x38)
        maximum, current = struct.unpack_from("<ii", raw, self.o["vital_max"])
        flat, percent = struct.unpack_from("<ii", raw, self.o["vital_reserved_flat"])
        available = usable_vital(maximum, flat, percent)
        if not 0 <= current <= maximum:
            raise ValueError("Current vital is outside its maximum")
        return maximum, current, available

    def buffs(self, component):
        self.buff_read_complete = True
        raw = self.vector(component + self.o["buffs_vector"], limit=512)
        result = []
        for i in range(0, len(raw), 8):
            try:
                address = struct.unpack_from("<Q", raw, i)[0]
                record = self.memory.read(address, 0x30)
                if struct.unpack_from("<Q", record)[0] != component:
                    raise ValueError("Buff owner mismatch")
                definition = struct.unpack_from("<Q", record, self.o["buff_definition"])[0]
                name = self.utf16(self.q(definition))
                if not re.fullmatch(r"[a-zA-Z0-9_/-]{1,200}", name):
                    raise ValueError("Unknown buff identifier encoding")
                remaining, duration = struct.unpack_from("<ff", record, self.o["buff_time"])
                if math.isnan(remaining) or remaining < 0:
                    continue
                result.append({"id": name, "name": name.replace("_", " "),
                               "remaining": remaining if math.isfinite(remaining) else None,
                               "duration": duration if math.isfinite(duration) else None,
                               "flask": name.startswith("flask_effect_")})
            except (OSError, ValueError, UnicodeError):
                self.buff_read_complete = False
        return result

    def entity_addresses(self, session):
        head, count = struct.unpack("<QQ", self.memory.read(session + self.o["entities_tree"], 16))
        if not 0 <= count <= 10000:
            raise ValueError("Entity count is outside limits")
        stack = [self.q(head + 8)] if count else []
        seen, result = set(), []
        while stack:
            node = stack.pop()
            if not node or node == head or node in seen:
                continue
            if len(seen) >= count + 32:
                raise ValueError("Entity tree exceeded its declared size")
            seen.add(node)
            raw = self.memory.read(node, 0x30)
            if raw[self.o["tree_nil"]]:
                continue
            stack.extend(struct.unpack_from("<Q", raw, off)[0] for off in (0, 16))
            result.append(struct.unpack_from("<Q", raw, self.o["tree_entity"])[0])
        if len(result) > count:
            raise ValueError("Entity tree changed while reading")
        return result

    def scene_addresses(self, session, epoch, diagnostics):
        if self.scene_epoch != epoch:
            self.scene_epoch = epoch
            self.scene_addresses_cache = []
            self.scene_identities.clear()
            self.display_names.clear()
            self.object_availability.clear()
        error = None
        for _ in range(2):
            try:
                addresses = self.entity_addresses(session)
                self.scene_addresses_cache = addresses
                self.scene_scan_at = time.monotonic()
                present = set(addresses)
                self.entity_cache = {a:c for a,c in self.entity_cache.items() if a in present}
                self.scene_identities = {a:i for a,i in self.scene_identities.items() if a in present}
                self.display_names = {a:n for a,n in self.display_names.items() if a in present}
                self.object_availability = {a:n for a,n in self.object_availability.items() if a in present}
                return addresses, False
            except (OSError, ValueError) as exc:
                error = exc
        # These addresses are only discovery candidates. Their identity, owner,
        # position and life are reread below; previous health is never reused.
        if self.scene_addresses_cache and time.monotonic() - self.scene_scan_at < .15:
            diagnostics['entity_scan'] = 'Retrying changing entity list; refreshing known entities'
            return self.scene_addresses_cache, True
        raise error

    def owned_component(self, pointer, entity, size):
        raw = self.memory.read(pointer, max(16, size))
        if struct.unpack_from('<Q', raw, 8)[0] != entity:
            raise ValueError('Scene component owner changed')
        return raw

    def observe_object_availability(self, address, identity, available, now):
        previous = self.object_availability.get(address)
        if previous is None or previous[0] != identity:
            previous = (identity,False,None)
        _,seen_available,unavailable_since = previous
        if available:
            self.object_availability[address] = (identity,True,None)
            return False
        if seen_available and unavailable_since is None:
            unavailable_since = now
        self.object_availability[address] = (identity,seen_available,unavailable_since)
        # Debounce temporary lockouts/activation animation. An object first
        # loaded as unavailable is not assumed to have been consumed.
        return bool(seen_available and now-unavailable_since >= .5)

    def native_icon_name(self,component,owner):
        offset=self.o.get('minimap_icon_definition')
        if offset is None:return ''
        raw=self.owned_component(component,owner,offset+8)
        definition=struct.unpack_from('<Q',raw,offset)[0]
        if not definition:return ''
        name=self.utf16(self.q(definition+self.o.get('minimap_icon_name',0)),maximum=128)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name):return ''
        self.owned_component(component,owner,16)
        return name

    def scene_entity(self, address, grid, matrix, viewport, recovered=False):
        header = self.memory.read(address, max(0x90, self.o.get('entity_id', 0)+4))
        identity = struct.unpack_from('<I', header, self.o['entity_id'])[0] if 'entity_id' in self.o else address
        if recovered and self.scene_identities.get(address) != identity:
            return None
        definition = struct.unpack_from('<Q', header, self.o['entity_definition'])[0]
        start, end, capacity = struct.unpack_from('<QQQ', header, self.o['entity_components'])
        if not start <= end <= capacity or (end-start)%8 or end-start > 128*8:
            raise ValueError('Invalid scene component vector')
        pointers = self.memory.read(start, end-start) if end>start else b''
        cache = self.entity_cache.get(address)
        if cache is None or cache[:3] != (definition, identity, pointers):
            path = self.path(address)
            found = self.components(address, raw=pointers)
            self.entity_cache[address] = (definition, identity, pointers, path, found)
            self.display_names.pop(address, None)
        else:
            path, found = cache[3:]
        self.scene_identities[address] = identity
        actor_info=classify_actor(path,found)
        monster = not actor_info and ('Monster' in found or path.startswith('Metadata/Monsters/'))
        object_info = actor_info or(None if monster else classify_object(path, found))
        native_icon=''
        if not monster and 'MinimapIcon'in found and 'Positioned'in found:
            try:
                native_icon=self.native_icon_name(found['MinimapIcon'],address)
                if not object_info and native_icon=='Breach':object_info=('breach','Breach')
            except (OSError,ValueError,UnicodeError):pass
        if (not monster and not object_info) or 'Positioned' not in found:
            return None
        positioned = self.owned_component(found['Positioned'], address, self.o['positioned_grid'] + 8)
        gx, gy = struct.unpack_from('<ii', positioned, self.o['positioned_grid'])
        if not 0 <= gx < len(grid[0]) or not 0 <= gy < len(grid):
            return None
        category, label = ('unknown', path.rsplit('/',1)[-1].split('@',1)[0]) if monster else object_info
        kind = 'monster' if monster else ('exit' if category == 'exit' else 'quest' if category == 'quest' else 'valuable')
        entry = dict(id=identity, address=address, kind=kind, category=category,
                     name=label, metadata=path, grid=(gx,gy),native_icon=native_icon)
        if actor_info and 'Life'in found:
            offset=self.o['life_vital']
            raw=self.owned_component(found['Life'],address,offset+0x38)
            maximum,current=struct.unpack_from('<ii',raw,offset+self.o['vital_max'])
            if maximum>0 and current==0:return None
        if monster:
            reaction_offset = self.o.get('positioned_reaction')
            entry['hostile'] = (positioned[reaction_offset] & 127) != 1 if reaction_offset is not None else None
            entry['rarity'] = None
            if 'ObjectMagicProperties' in found and 'monster_rarity' in self.o:
                offset = self.o['monster_rarity']
                raw = self.owned_component(found['ObjectMagicProperties'], address, offset+4)
                rarity = struct.unpack_from('<i', raw, offset)[0]
                if rarity not in range(4):
                    raise ValueError('Unknown monster rarity')
                entry['rarity'] = rarity
                if rarity == 3:
                    entry['kind'] = 'unique'
                    try:
                        entry['is_map_boss']=self.monster_boss(found['ObjectMagicProperties'],address)
                    except (OSError,ValueError,UnicodeError):
                        entry['is_map_boss']=None
                    if entry['is_map_boss'] is True:entry['kind']='boss'
            if 'Life' in found:
                offset = self.o['life_vital']
                raw = self.owned_component(found['Life'], address, offset+0x38)
                maximum, current = struct.unpack_from('<ii', raw, offset+self.o['vital_max'])
                flat, percent = struct.unpack_from('<ii', raw, offset+self.o['vital_reserved_flat'])
                usable = usable_vital(maximum, flat, percent)
                if not 0 <= current <= maximum:
                    raise ValueError('Invalid monster life')
                entry.update(life=current, max_life=usable, alive=current > 0)
        if 'Render' in found:
            raw = self.owned_component(found['Render'], address, self.o['render_position']+12)
            world = struct.unpack_from('<fff', raw, self.o['render_position'])
            if all(math.isfinite(v) for v in world):
                entry['map_grid'] = (world[0]*23/250, world[1]*23/250)
                entry['health_world'] = world
                entry['health_camera'] = (matrix,viewport)
            screen = project(matrix, world, *viewport)
            if screen:
                entry['screen'] = screen
            if 'render_name' in self.o:
                if address not in self.display_names:
                    try:
                        self.display_names[address] = self.native_string(found['Render']+self.o['render_name'])
                    except (ValueError,OSError,UnicodeError):
                        pass
                native_name=self.display_names.get(address)
                entry['name']=(native_name or label)if monster else preferred_object_name(native_name,label)
        if not monster and 'Chest' in found and 'chest_opened' in self.o:
            offset = self.o['chest_opened']
            raw = self.owned_component(found['Chest'], address, offset+1)
            if raw[offset] not in (0,1):
                raise ValueError('Unknown chest state')
            entry['used'] = bool(raw[offset])
        if not monster and 'Shrine' in found and 'shrine_used' in self.o:
            offset = self.o['shrine_used']
            raw = self.owned_component(found['Shrine'],address,offset+1)
            if raw[offset] not in (0,1):
                raise ValueError('Unknown shrine state')
            entry['used'] = bool(raw[offset])
        if not monster and 'Targetable' in found and 'targetable' in self.o:
            try:
                offset = self.o['targetable']
                raw = self.owned_component(found['Targetable'],address,offset+1)
                if raw[offset] in (0,1):
                    entry['available'] = bool(raw[offset])
                    if category=='eldritch' and not entry['available']:entry['used']=True
                    if 'used' not in entry and category not in {'waypoint','exit','portal','masters','harbinger'}:
                        entry['used'] = self.observe_object_availability(address,identity,entry['available'],time.monotonic())
            except (OSError,ValueError):
                pass
        return entry

    def read_visual(self, memory, window, snapshot):
        """Fresh visual poses/vitals for known living actors; no scene traversal."""
        self.visual_invalidated=False
        context = getattr(snapshot, 'visual_context', None)
        if not context or not 0<=time.monotonic()-snapshot.captured_at<=2 or window.pid != context['pid']:
            return None
        self.memory = memory
        base, state, session = context['base'], context['state'], context['session']
        def valid():
            return (self.q(base+self.o['state_root_rva']) == state and
                self.q(state) == base+self.o['state_vtable_rva'] and
                self.q(state+self.o['state_session']) == session and
                self.q(session) == base+self.o['session_vtable_rva'] and
                self.q(session+self.o['local_player']) == context['player'] and
                self.q(session+self.o['current_area']) == context['area_record'] and
                self.integer(base+self.o['area_counter_rva']) == context['counter'] and
                self.integer(session+self.o['area_hash']) == context['area_hash'])
        if not valid():
            self.visual_invalidated=True;return None
        actors = {}
        for record in context['actors'][:256]:
            address, identity, render, life, expected_pointers = record
            key = (identity, address)
            try:
                header = memory.read(address,0x90)
                if struct.unpack_from('<I', header,self.o['entity_id'])[0] != identity:
                    actors[key] = None
                    continue
                start,end,capacity = struct.unpack_from('<QQQ',header,self.o['entity_components'])
                if not start<=end<=capacity or (end-start)%8 or not 0<end-start<=128*8:
                    raise ValueError('Invalid visual component vector')
                pointers = memory.read(start,end-start)
                if pointers != expected_pointers:
                    current_pointers = set(struct.unpack(f'<{len(pointers)//8}Q',pointers))
                    if render not in current_pointers or life not in current_pointers:
                        raise ValueError('Visual actor components replaced')
                raw = self.owned_component(life, address, self.o['life_vital']+0x38)
                offset = self.o['life_vital']
                maximum,current = struct.unpack_from('<ii',raw,offset+self.o['vital_max'])
                flat,percent = struct.unpack_from('<ii',raw,offset+self.o['vital_reserved_flat'])
                usable = usable_vital(maximum,flat,percent)
                if not 0 <= current <= maximum:
                    raise ValueError('Invalid visual actor life')
                entry = dict(life=current,max_life=usable,alive=current>0)
                if current>0:
                    raw = self.owned_component(render,address,self.o['render_position']+12)
                    world = struct.unpack_from('<fff',raw,self.o['render_position'])
                    if not all(math.isfinite(v) for v in world):
                        raise ValueError('Invalid visual actor position')
                    entry.update(world=world,map_grid=(world[0]*23/250,world[1]*23/250))
                actors[key] = entry
            except (OSError,ValueError):
                # A racing/missing pose read is not evidence that the actor died.
                # Omit this update; confirmed life=0 above still removes the bar.
                pass
        # Sample the camera after actor reads, rather than projecting actors
        # against a matrix captured before a variable-length full scene scan.
        frame = self.q(state+self.o['frame_context'])
        matrix = struct.unpack('<16f',memory.read(frame+self.o['camera_matrix'],64))
        viewport = struct.unpack('<ii',memory.read(frame+self.o['camera_viewport'],8))
        if not valid():
            self.visual_invalidated=True;return None
        if not all(100<=v<=32768 for v in viewport):return None
        player_world = None
        map_transform=None
        if context.get('player_render'):
            raw = self.owned_component(context['player_render'],context['player'],self.o['render_ground_height']+4)
            world = struct.unpack_from('<fff',raw,self.o['render_position'])
            ground = struct.unpack_from('<f',raw,self.o['render_ground_height'])[0]
            if all(math.isfinite(v) for v in (*world,ground)):
                player_world = (world[0],world[1],ground)
                map_player=(world[0]*23/250,world[1]*23/250)
                if snapshot.terrain_heights is not None:
                    shift=ground*23/500
                    map_player=(map_player[0]-shift,map_player[1]-shift)
                map_transform=self.native_map(state,map_player,viewport)
        if not valid():
            self.visual_invalidated=True;return None
        for entry in actors.values():
            if entry and entry.get('world'):
                entry['health_world'] = entry.pop('world')
                entry['screen'] = project(matrix,entry['health_world'],*viewport)
        result=dict(key=context['key'],captured_at=time.monotonic(),actors=actors,matrix=matrix,viewport=viewport,
                    player_world=player_world)
        if player_world is not None:result['map_transform']=map_transform
        return result

    def terrain(self, session, area):
        width = self.integer(session + self.o["terrain_columns"]) * self.o["tile_cells"]
        height = self.integer(session + self.o["terrain_rows"]) * self.o["tile_cells"]
        stride = self.integer(session + self.o["terrain_stride"])
        start, end, capacity = struct.unpack("<QQQ", self.memory.read(session + self.o["terrain_melee"], 24))
        if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 32_000_000 or not start <= end <= capacity:
            raise ValueError("Invalid terrain dimensions or allocation")
        if end - start != stride * height:
            raise ValueError("Terrain dimensions do not match allocation")
        key = (session, area, start, end, width, height, stride)
        if key != self.grid_key:
            self.grid = unpack_terrain(self.memory.read(start, end - start), width, height, stride)
            self.grid_regions = walkable_regions(self.grid)
            self.grid_key = key
        return self.grid

    def terrain_heights(self, session):
        if self.height_key != self.grid_key:
            columns = self.integer(session + self.o['terrain_columns'])
            rows = self.integer(session + self.o['terrain_rows'])
            if self.integer(session + self.o['terrain_height_multiplier']) != 1:
                raise ValueError('Terrain height multiplier requires validation')
            tiles = self.vector(session + self.o['terrain_tiles'], stride=56, limit=100000)
            self.height_grid = decode_height_tiles(tiles, columns, rows,
                lambda pointer: self.vector(pointer, stride=1, limit=529))
            self.height_key = self.grid_key
        return self.height_grid

    def terrain_landmarks(self, session):
        if 'tile_file' not in self.o:return []
        if self.landmarks_key == self.grid_key:return self.landmarks
        columns=self.integer(session+self.o['terrain_columns'])
        rows=self.integer(session+self.o['terrain_rows'])
        stride=self.o['tile_record_size']
        raw=self.vector(session+self.o['terrain_tiles'],stride=stride,limit=100000)
        if not 0<columns*rows<=100000 or len(raw)!=columns*rows*stride:
            raise ValueError('Landmark tile allocation does not match terrain')
        descriptions={};landmarks=[]
        for index in range(columns*rows):
            pointer=struct.unpack_from('<Q',raw,index*stride+self.o['tile_file'])[0]
            if pointer not in descriptions:
                if len(descriptions)>=4096:raise ValueError('Too many unique landmark descriptions')
                try:
                    path=self.native_string(pointer+self.o['tile_path'],maximum=512)
                    detail=self.q(pointer+self.o['tile_detail'])
                    name=self.native_string(detail+self.o['tile_name'],maximum=128) if detail else ''
                    if not path.startswith('Metadata/Terrain/'):
                        raise ValueError('Invalid terrain asset path')
                    descriptions[pointer]=(name,path)
                except (OSError,ValueError,UnicodeError):descriptions[pointer]=('','')
            name,path=descriptions[pointer]
            if path:
                landmarks.append(dict(name=name,path=path,grid=(index%columns*23,index//columns*23)))
        self.landmarks_key,self.landmarks=self.grid_key,landmarks
        return landmarks

    def read(self, memory, window):
        self.memory = memory
        base = memory.main_image()
        if self.pid != window.pid or self.base != base:
            self.names.clear()
            self.paths.clear()
            self.grid_key = None
            self.height_key = None
            self.height_grid = None
            self.entity_cache.clear()
            self.scene_epoch = None
            self.landmarks_key = None
            self.preload_key = None
            self.inventory_at = 0
            self.inventory_epoch = None
            self.base, self.pid = base, window.pid
        state = self.q(base + self.o["state_root_rva"])
        if self.q(state) != base + self.o["state_vtable_rva"]:
            raise ValueError("In-game state vtable does not match this profile")
        session = self.q(state + self.o["state_session"])
        if not session:
            return Snapshot(source="live", captured_at=time.monotonic())
        if self.q(session) != base + self.o["session_vtable_rva"]:
            raise ValueError("Current session vtable mismatch")
        player = self.q(session + self.o["local_player"])
        if not player:
            return Snapshot(source="live", captured_at=time.monotonic())
        metadata = self.path(player)
        if not metadata.startswith("Metadata/Characters/"):
            raise ValueError("Local player is not a character entity")
        components = self.components(player)
        if not {"Player", "Life", "Positioned"} <= components.keys():
            raise ValueError("Local player is missing required components")
        maximum, life, available = self.life(components["Life"])
        max_mana, mana, usable_mana = self.life(components["Life"], mana=True)
        area_record = self.q(session + self.o["current_area"])
        area_id = self.utf16(self.q(area_record))
        area_name = self.utf16(self.q(area_record + 8))
        if not re.fullmatch(r"[A-Za-z0-9_/-]{1,200}", area_id):
            raise ValueError("Area identifier is invalid")
        counter = self.integer(base + self.o["area_counter_rva"])
        area_hash = self.integer(session + self.o["area_hash"])
        epoch = (session, area_id, area_hash, counter)
        if getattr(self, "area_epoch", None) != epoch:
            self.entity_cache.clear()
            self.paths.clear()
            self.grid_key = None
            self.area_id = area_id
            self.area_epoch = epoch
        grid = self.terrain(session, epoch)
        x, y = struct.unpack("<ii", self.memory.read(components["Positioned"] + self.o["positioned_grid"], 8))
        if not (0 <= x < len(grid[0]) and 0 <= y < len(grid)):
            raise ValueError("Local player position is outside decoded terrain")
        frame = self.q(state + self.o["frame_context"])
        matrix = struct.unpack("<16f", self.memory.read(frame + self.o["camera_matrix"], 64))
        viewport = struct.unpack("<ii", self.memory.read(frame + self.o["camera_viewport"], 8))
        if not all(100 <= dimension <= 32768 for dimension in viewport):
            raise ValueError("Camera viewport is invalid")
        diagnostics = {}
        entities = []
        recovered = False
        try:
            addresses, recovered = self.scene_addresses(session, epoch, diagnostics)
        except (OSError, ValueError) as exc:
            addresses = []
            diagnostics['entities'] = str(exc)
            diagnostics['hazards'] = 'Entity list unavailable'
        for address in addresses:
            if address == player:
                continue
            for attempt in range(2):
                try:
                    entry = self.scene_entity(address, grid, matrix, viewport, recovered)
                    if entry is not None:
                        entities.append(entry)
                    break
                except (OSError, ValueError, UnicodeError):
                    self.entity_cache.pop(address, None)
                    self.display_names.pop(address, None)
        try:
            heights = self.terrain_heights(session)
        except (OSError, ValueError, UnicodeError) as exc:
            heights = None
            diagnostics['height'] = str(exc)
        try:
            landmarks=self.terrain_landmarks(session)
        except (OSError,ValueError,UnicodeError) as exc:
            landmarks=[]
            diagnostics['landmarks']=str(exc)
        self.buff_read_complete = False
        try:
            buffs = self.buffs(components['Buffs']) if 'Buffs' in components else []
            if not self.buff_read_complete:
                diagnostics['buffs'] = 'Incomplete buff records'
        except (OSError, ValueError, UnicodeError) as exc:
            buffs = []
            diagnostics['buffs'] = str(exc)
        try:
            preloads = self.preloads(counter)
        except (OSError, ValueError, UnicodeError) as exc:
            preloads = []
            diagnostics['preloads'] = str(exc)
        self.ui_layout_headers={}
        self.item_panels=[]
        try:
            stash, tabs = self.inventories(session, epoch)
            assess_inventory=False
            if getattr(self,'inventory_assessment_enabled',False) and 'ui_inventory' in self.o:
                ui=self.q(state+self.o['state_ui']);panel=self.q(ui+self.o['ui_inventory'])
                assess_inventory=bool(panel and self.element_rect(panel,viewport))
            inventory=self.carried_items(session,epoch,assessment=assess_inventory) if getattr(self,'read_item_overlays',False) else []
            self.stash_layout(state, stash+inventory, viewport)
        except (OSError, ValueError, UnicodeError) as exc:
            stash, tabs,inventory = [], [],[]
            diagnostics['stash'] = str(exc)
        hovered=None
        if getattr(self,'read_item_overlays',False):
            try:hovered=self.hovered_item(state,viewport)
            except (OSError,ValueError,UnicodeError):pass
        ground=[]
        if getattr(self,'read_item_overlays',False):
            try:ground=self.ground_labels(state,viewport)
            except (OSError,ValueError,UnicodeError) as exc:diagnostics['ground_items']=str(exc)
        self.ui_layout_headers=None
        hazards = [dict(entry, name="Volatile core", active=True, radius=28)
                   for entry in entities if entry["metadata"].startswith("Metadata/Monsters/VolatileCore/VolatileCore")]
        if (self.q(base + self.o["state_root_rva"]) != state or
                self.q(state + self.o["state_session"]) != session or
                self.q(session + self.o["local_player"]) != player or
                self.q(session + self.o["current_area"]) != area_record or
                self.integer(base + self.o["area_counter_rva"]) != counter or
                self.integer(session + self.o["area_hash"]) != area_hash):
            raise ValueError("Game area changed during the read")
        snapshot = Snapshot(source="live", captured_at=time.monotonic(), area=area_name,
                            in_game=True, loading=False,
                            town=town_or_hideout(area_id,area_name),
                            life=life, max_life=available,
                            mana=mana, max_mana=usable_mana, player_grid=(x, y), grid=grid,
                            map_scale=min(620 / len(grid[0]), 580 / len(grid)),
                            entities=entities, buffs=buffs, preloads=preloads,
                            stash=[dict(item) for item in stash], hazards=hazards,
                            capabilities={"terrain", "entities", "health", "buffs", "preloads", "stash", "hazards"})
        snapshot.stash_tabs = tabs
        snapshot.inventory=[dict(item)for item in inventory]
        snapshot.inventory_loaded=bool(getattr(self,'read_item_overlays',False)and getattr(self,'carried_loaded',False)and 'stash'not in diagnostics)
        snapshot.hovered_item=hovered
        snapshot.instance_key=epoch
        snapshot.ground_items=ground
        snapshot.item_panels=list(self.item_panels)
        snapshot.viewport=tuple(viewport)
        snapshot.terrain_heights = heights
        snapshot.walkable_regions = self.grid_regions
        snapshot.area_id=area_id
        snapshot.landmarks=landmarks
        snapshot.diagnostics = diagnostics
        snapshot.capabilities -= diagnostics.keys()
        if 'Render' in components:
            world = struct.unpack('<fff', self.memory.read(components['Render'] + self.o['render_position'], 12))
            map_player = (world[0] * 23 / 250, world[1] * 23 / 250)
        else:
            map_player = (x + .5, y + .5)
        if 'Render' in components and heights is not None:
            ground = struct.unpack('<f', self.memory.read(components['Render'] + self.o['render_ground_height'], 4))[0]
            if not math.isfinite(ground) or abs(ground) > 100000:
                raise ValueError('Invalid player ground height')
            shift = ground * 23 / 500
            map_player = (map_player[0] - shift, map_player[1] - shift)
        else:
            map_player = terrain_grid_point(heights, map_player)
        snapshot.map_transform = self.native_map(state, map_player, viewport)
        snapshot.total_life = maximum
        snapshot.total_mana = max_mana
        snapshot.area_id = area_id
        snapshot.entity_count = len(self.entity_cache) + 1
        snapshot.camera = dict(matrix=matrix,viewport=viewport,captured_at=snapshot.captured_at)
        if 'Render' in components:
            snapshot.player_world = (world[0],world[1],ground) if heights is not None else tuple(world)
        actors = []
        for entity in entities:
            cached = self.entity_cache.get(entity['address'])
            if (cached and entity.get('alive') and entity.get('screen') and entity.get('hostile') is not False):
                found = cached[4]
                if 'Render' in found and 'Life' in found:
                    actors.append((entity['address'],entity['id'],found['Render'],found['Life'],cached[2]))
        snapshot.visual_context = dict(key=(self.pid,base,state,session,counter,area_hash,id(grid)),
            pid=self.pid,base=base,state=state,session=session,player=player,area_record=area_record,
            counter=counter,area_hash=area_hash,actors=tuple(actors),player_render=components.get('Render'))
        return snapshot
