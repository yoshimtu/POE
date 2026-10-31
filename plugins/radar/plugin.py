import math

from exile.model import Mark, Plugin
from exile.mapview import map_point, map_clip
from exile.radar import CATEGORIES, monster_category
from exile.areas import safe_area
from exile.map_icons import icon_key


class Radar(Plugin):
    id, name, category = 'radar', 'Monster & object radar', 'Navigation'
    description = 'Native map icons, rarity markers, enemy health bars and league encounters.'
    requires = {'entities'}
    radar_categories = CATEGORIES
    defaults = dict(map_icons=True,icon_scale=100,monsters=True, objects=True, zoom=100, max_range=0,
                    filled=True, circle_width=1, opacity=90, refresh_rate='120 fps',
                    health_bars=True, health_filter='Rare and unique', health_anchor='Above enemies',
                    health_width=90, health_height=6, health_offset=30, health_names=False,
                    health_percent=False, health_smoothing=8, hide_used=True)
    fields = {
        'map_icons':('Use map icons','bool'),
        'icon_scale':('Icon scale %','int',50,200),
        'monsters': ('Show monster markers', 'bool'),
        'objects': ('Show object markers', 'bool'),
        'zoom': ('Map alignment scale %', 'int', 25, 300),
        'max_range': ('Marker range in terrain cells (0 = all loaded)', 'int', 0, 3000),
        'filled': ('Filled circles', 'bool'),
        'circle_width': ('Circle border width (pixels)', 'int', 1, 3),
        'opacity': ('Marker opacity %', 'int', 20, 100),
        'refresh_rate': ('Overlay drawing rate', 'choice', ['60 fps', '90 fps', '120 fps', '144 fps']),
        'hide_used': ('Hide used objects when their state is known', 'bool'),
        'health_bars': ('Show enemy health bars', 'bool'),
        'health_filter': ('Show bars for', 'choice', ['All enemies', 'Magic, rare and unique', 'Rare and unique', 'Unique only']),
        'health_anchor': ('Health-bar position', 'choice', ['Above enemies', 'On map']),
        'health_width': ('Bar width (pixels)', 'int', 30, 180),
        'health_height': ('Bar height (pixels)', 'int', 3, 12),
        'health_offset': ('Height above enemy (pixels)', 'int', 0, 100),
        'health_names': ('Enemy names above bars', 'bool'),
        'health_percent': ('Health percentage', 'bool'),
        'health_smoothing': ('Position smoothing (ms; 0 = minimum delay)', 'int', 0, 40),
    }
    for key, title, group, color, size, show, label in CATEGORIES:
        defaults.update({f'show_{key}': show, f'size_{key}': size,
                         f'color_{key}': color, f'label_{key}': label})
        fields.update({f'show_{key}': (f'{title}: enabled', 'bool'),
                       f'size_{key}': (f'{title}: size', 'int', 1, 16),
                       f'color_{key}': (f'{title}: color', 'color'),
                       f'label_{key}': (f'{title}: label', 'bool')})

    def migrate_settings(self, saved):
        settings = dict(saved.get('radar', {}).get('settings', {}))
        old = saved.get('health', {}).get('settings', {})
        if settings.get('labels') is False:
            for category in CATEGORIES:
                settings.setdefault(f'label_{category[0]}', False)
        if 'health_width' not in settings and 'width' in old:
            settings['health_width'] = old['width']
        if 'health_filter' not in settings and 'rare_only' in old:
            settings['health_filter'] = 'Rare and unique' if old['rare_only'] else 'All enemies'
        return settings

    def tick(self, snapshot, ctx):
        result = []
        hide_objects=safe_area(snapshot)
        map_available = snapshot.source != 'live' or bool(snapshot.map_transform)
        for entity in snapshot.entities[:10000]:
            monster = entity.get('kind') in ('monster', 'magic', 'rare', 'unique', 'boss')
            if hide_objects and not monster:continue
            category = monster_category(entity) if monster else entity.get('category', entity.get('kind'))
            if category=='masters' and '/leagueexpedition/npc/' in entity.get('metadata','').casefold():continue
            if category=='recipe' and snapshot.source=='live':
                # Account unlocks are not decoded: use the requested campaign-only fallback.
                if not snapshot.area_id.casefold().startswith(('1_','2_')):continue
                if entity.get('available') is False:continue
            if category=='eldritch' and entity.get('available') is False:continue
            if category == 'valuable':
                category = 'strongbox'
            if f'show_{category}' not in self.settings:
                continue
            if monster:
                current, maximum = entity.get('life'), entity.get('max_life')
                if (entity.get('alive') is False or current is None or maximum is None or
                        not math.isfinite(current) or not math.isfinite(maximum) or not 0 < current <= maximum):
                    continue
            elif self.settings['hide_used'] and entity.get('used') is True:
                continue
            color = self.settings[f'color_{category}']
            point = entity.get('grid')
            in_range = bool(point)
            if point and self.settings['max_range'] and snapshot.player_grid:
                in_range = math.dist(point, snapshot.player_grid) <= self.settings['max_range']
            allowed = self.settings['monsters' if monster else 'objects'] and self.settings[f'show_{category}']
            map_grid = entity.get('map_grid') or ((point[0]+.5,point[1]+.5) if point else None)
            map_position = (map_point(snapshot, map_grid, self.settings['zoom'])
                            if map_available and point else None)
            if allowed and in_range and map_position:
                result.append(Mark('dot', *map_position,
                    entity.get('name', '') if self.settings[f'label_{category}'] else '', color,
                    self.settings[f'size_{category}'], value=self.settings['opacity']/100,
                    clip=map_clip(snapshot), payload=dict(filled=self.settings['filled'],
                                                        width=self.settings['circle_width'],
                                                        icon=icon_key(entity,category)if self.settings['map_icons']else'',
                                                        icon_scale=self.settings['icon_scale'],
                                                        icon_minimum=8 if category=='normal' else 12,
                                                        icon_tint=color if category in ('normal','magic')else'')))
            if not monster or category == 'friendly' or not self.settings['health_bars'] or 'health' not in snapshot.capabilities:
                continue
            threshold = {'All enemies': 0, 'Magic, rare and unique': 1, 'Rare and unique': 2, 'Unique only': 3}[self.settings['health_filter']]
            if category not in ('normal', 'magic', 'rare', 'unique') or ('normal','magic','rare','unique').index(category) < threshold:
                continue
            position = entity.get('screen') if self.settings['health_anchor'] == 'Above enemies' else map_position
            if not position:
                continue
            text = entity.get('name', '') if self.settings['health_names'] else ''
            if self.settings['health_percent']:
                text = f'{text} {100*current/maximum:.0f}%'.strip()
            result.append(Mark('bar', position[0], position[1]-self.settings['health_offset'], text,
                color, self.settings['health_width'], current/maximum,
                clip=map_clip(snapshot) if self.settings['health_anchor'] == 'On map' else None,
                payload=dict(height=self.settings['health_height'], entity_id=entity.get('id'),
                             entity_address=entity.get('address'), category=category)))
        return result


def create_plugin():
    return Radar()
