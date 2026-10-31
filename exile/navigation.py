"""Bounded A* routing; never issues movement inputs."""
import heapq
import math
import time


def route(grid: list[list[int]], start: tuple[int, int], goal: tuple[int, int],
          limit: int = 100_000, walk_values=None, cancel=None, stats=None) -> list[tuple[int, int]]:
    if stats is not None: stats.update(status='invalid',visited=0)
    if not grid or not grid[0] or len(grid) > 8192 or len(grid[0]) > 8192 or len(grid)*len(grid[0])>32_000_000:
        return []
    width, height = len(grid[0]), len(grid)
    if any(len(row) != width for row in grid):
        return []

    def walk(p):
        return (0 <= p[0] < width and 0 <= p[1] < height and
                (bool(grid[p[1]][p[0]]) if walk_values is None else grid[p[1]][p[0]] in walk_values))

    def heuristic(p):
        dx,dy=abs(p[0]-goal[0]),abs(p[1]-goal[1])
        return max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy)

    if not walk(start) or not walk(goal):
        return []
    queue = [(heuristic(start), 0., start)]
    costs = {start: 0.}
    parents = {}
    visited = 0
    while queue and visited < limit:
        _, cost, current = heapq.heappop(queue)
        if cost != costs[current]:
            continue
        visited += 1
        if visited%256==0:
            if cancel is not None and cancel.is_set():
                if stats is not None: stats.update(status='cancelled',visited=visited)
                return []
            if visited%4096==0: time.sleep(0)
        if current == goal:
            result = [current]
            while current in parents:
                current = parents[current]
                result.append(current)
            if stats is not None: stats.update(status='ready',visited=visited,cost=cost)
            return result[::-1]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            neighbor = (current[0] + dx, current[1] + dy)
            if not walk(neighbor):
                continue
            if dx and dy and (not walk((current[0] + dx, current[1])) or
                              not walk((current[0], current[1] + dy))):
                continue
            score = cost + (math.sqrt(2) if dx and dy else 1)
            if score < costs.get(neighbor, float("inf")):
                parents[neighbor] = current
                costs[neighbor] = score
                heapq.heappush(queue, (score + heuristic(neighbor), score, neighbor))
    if stats is not None: stats.update(status='limit' if queue else 'unreachable',visited=visited)
    return []
