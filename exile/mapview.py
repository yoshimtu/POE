"""Shared affine projection for terrain, routes and radar on PoE's visible map."""
import math
import time
from collections import deque
from exile.terrain import terrain_grid_point
from exile.projection import project


class MapMotion:
    """Interpolate visual positions only; health and input data stay untouched."""
    def __init__(self, delay=1 / 30):
        self.delay = delay
        self.key = None
        self.previous = None
        self.current = None
        self.history = deque(maxlen=32)

    def sample(self, snapshot, now=None):
        transform = snapshot.map_transform
        if snapshot.source != 'live' or not transform:
            self.key = self.previous = self.current = None
            self.history.clear()
            return transform
        now = time.monotonic() if now is None else now
        key = (snapshot.area, id(snapshot.grid), transform['mode'], transform['clip'],
               transform['basis_x'], transform['basis_y'])
        sample = (getattr(snapshot,'map_captured_at',snapshot.captured_at), dict(transform))
        if key != self.key or self.current is None:
            self.key, self.current, self.previous = key, sample, None
            self.history.clear()
            self.history.append(sample)
            return transform
        if sample[0] > self.current[0]:
            if (sample[0] - self.current[0] > .2 or
                    math.dist(self.current[1]['player'], transform['player']) > 50):
                self.history.clear()
            self.previous, self.current = self.current, sample
            self.history.append(sample)
        # A fixed visual delay can span several samples. Keeping only the last
        # pair snaps to the older endpoint whenever reads arrive faster than
        # that delay, even with perfectly regular input and rendering.
        target = now - self.delay
        while len(self.history) > 2 and self.history[1][0] <= target:
            self.history.popleft()
        start, before = self.history[0]
        if len(self.history) == 1 or target <= start:
            return dict(before)
        end, after = self.history[1]
        alpha = max(0., min(1., (target - start) / (end - start)))
        result = dict(after)
        for field in ('player', 'center'):
            result[field] = tuple(a + (b - a) * alpha for a, b in zip(before[field], after[field]))
        return result


class EntityMotion:
    """Synchronize visual entity positions with the map's existing time delay.

    Life/rarity/hostility always come from the newest snapshot. A dead or missing
    entity is never kept alive by its position history. Navigation grids remain
    integers; only map_grid and screen positions are interpolated.
    """
    def __init__(self, delay=1/30):
        self.delay = delay
        self.health_delay = .008
        self.key = None
        self.histories = {}

    def sample(self, snapshot, now=None):
        if snapshot.source != 'live' or not snapshot.in_game or snapshot.loading:
            self.key = None
            self.histories.clear()
            return snapshot.entities
        now = time.monotonic() if now is None else now
        key = (snapshot.area, id(snapshot.grid))
        if key != self.key:
            self.key = key
            self.histories.clear()
        active, result = set(), []
        target = now-max(self.delay,self.health_delay)
        for entity in snapshot.entities:
            if entity.get('kind') not in ('monster','magic','rare','unique','boss') or entity.get('alive') is False:
                result.append(entity)
                continue
            identity = (entity.get('id'), entity.get('address'))
            if identity == (None,None):
                result.append(entity)
                continue
            active.add(identity)
            fields = ('map_grid','health_world') if entity.get('health_world') is not None else ('map_grid','screen')
            pose = {k:entity[k] for k in fields if entity.get(k) is not None}
            history = self.histories.setdefault(identity, deque(maxlen=32))
            at = entity.get('position_captured_at',snapshot.captured_at)
            if not history or at > history[-1][0]:
                if history:
                    old_at, old = history[-1]
                    if at-old_at > .2 or ('map_grid' in pose and 'map_grid' in old and
                                          math.dist(pose['map_grid'],old['map_grid']) > 50):
                        history.clear()
                history.append((at,pose))
            while len(history)>2 and history[1][0]<=target:
                history.popleft()
            visual = dict(entity)
            for field in pose:
                field_target = now-(self.health_delay if field=='health_world' else self.delay)
                before_at,before = history[0]
                after_at,after = history[0]
                for captured,position in history:
                    if captured<=field_target:
                        before_at,before = captured,position
                    after_at,after = captured,position
                    if captured>=field_target:
                        break
                if field not in before or field not in after:
                    continue
                alpha=max(0.,min(1.,(field_target-before_at)/(after_at-before_at))) if after_at>before_at else 0
                visual[field]=tuple(a+(b-a)*alpha for a,b in zip(before[field],after[field]))
            if visual.get('health_world') is not None and visual.get('health_camera'):
                matrix,viewport=visual['health_camera']
                visual['screen']=project(matrix,visual['health_world'],*viewport)
            result.append(visual)
        self.histories={identity:h for identity,h in self.histories.items() if identity in active}
        return result


def outline_rows(grid, thickness=2):
    """Keep the inside edge of walkable cells; wide rows use native integer ops."""
    if not grid:
        return []
    width = len(grid[0])
    if not 1 <= thickness <= 4 or not width or any(len(row) != width for row in grid):
        raise ValueError('Invalid outline dimensions')
    binary = bytes([0] + [1] * 255)
    bits = [int.from_bytes(bytes(row).translate(binary), 'little') for row in grid]
    rows = []
    for y, inside in enumerate(bits):
        interior = inside
        for step in range(1, thickness + 1):
            above = bits[y - step] if y >= step else 0
            below = bits[y + step] if y + step < len(bits) else 0
            interior &= above & below & (inside << (8 * step)) & (inside >> (8 * step))
        rows.append((inside & ~interior).to_bytes(width, 'little'))
    return rows


def map_point(snapshot, point, zoom=100, adjusted=False):
    transform = snapshot.map_transform
    if not transform:
        if snapshot.source == 'live':
            return None
        return (snapshot.map_origin[0] + point[0] * snapshot.map_scale,
                snapshot.map_origin[1] + point[1] * snapshot.map_scale)
    if not adjusted:
        point = terrain_grid_point(snapshot.terrain_heights, point)
    dx, dy = point[0] - transform['player'][0], point[1] - transform['player'][1]
    return (transform['center'][0] + (dx - dy) * transform['basis_x'] * zoom / 100,
            transform['center'][1] + (dx + dy) * transform['basis_y'] * zoom / 100)


def map_clip(snapshot):
    return snapshot.map_transform.get('clip') if snapshot.map_transform else None
