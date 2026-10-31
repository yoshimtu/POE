"""Independent tile-height decoding, checked against live reference samples."""
import numpy as np
import cv2

HEIGHT_UNIT = -7.8125
WORLD_TO_GRID = 23 / 250


def walkable_regions(grid):
    """Components match eight-way travel with diagonal corner cutting forbidden."""
    height=len(grid);width=len(grid[0])if height else 0
    if not 0<width<=8192 or not 0<height<=8192 or width*height>32_000_000 or any(len(row)!=width for row in grid):
        raise ValueError('Invalid region grid dimensions')
    cells=np.frombuffer(b''.join(bytes(row)for row in grid),dtype=np.uint8).reshape(height,width)
    # Every legal diagonal also has a legal orthogonal connection, so four-way
    # components describe the same reachable regions without crossing corners.
    _,regions=cv2.connectedComponents((cells>0).astype(np.uint8),connectivity=4)
    regions.flags.writeable=False
    return regions

_y, _x = np.indices((23, 23))
_rotations = ((_x, _y), (_y, 22 - _x), (22 - _x, 22 - _y),
              (22 - _y, _x), (22 - _x, _y), (22 - _y, 22 - _x),
              (_x, 22 - _y), (_y, _x))
ROTATION_INDEX = tuple((y * 23 + x).reshape(-1) for x, y in _rotations)


def decode_height_samples(payload):
    if not payload:
        return np.zeros(529, dtype=np.int16)
    if len(payload) == 1:
        value = payload[0] - 256 if payload[0] >= 128 else payload[0]
        return np.full(529, value, dtype=np.int16)
    bits = {69: 1, 137: 2, 281: 4, 529: 8}.get(len(payload))
    if bits is None:
        raise ValueError('Unknown terrain height encoding')
    data = np.frombuffer(payload, dtype=np.uint8)
    if bits == 8:
        return data.view(np.int8).astype(np.int16)
    palette_size = 1 << bits
    positions = np.arange(529) * bits
    indices = (data[palette_size + positions // 8] >> (positions % 8)) & (palette_size - 1)
    return data[:palette_size].view(np.int8)[indices].astype(np.int16)


def decode_height_tiles(tiles, columns, rows, read_samples):
    if not 0 < columns * 23 <= 8192 or not 0 < rows * 23 <= 8192 or columns * rows * 529 > 32_000_000:
        raise ValueError('Terrain height dimensions exceed limits')
    if len(tiles) != columns * rows * 56:
        raise ValueError('Tile-height allocation does not match dimensions')
    tile_type = np.dtype({'names': ['source', 'height', 'rotation'],
                          'formats': ['<u8', '<i2', 'u1'], 'offsets': [0, 48, 54], 'itemsize': 56})
    records = np.frombuffer(tiles, dtype=tile_type)
    result = np.empty((rows * 23, columns * 23), dtype=np.int16)
    samples, rotated = {}, {}
    for index, tile in enumerate(records):
        pointer, rotation, base = int(tile['source']), int(tile['rotation']), int(tile['height'])
        if rotation > 7 or not -16000 <= base <= 16000:
            raise ValueError('Invalid tile height or rotation')
        if pointer not in samples:
            samples[pointer] = decode_height_samples(read_samples(pointer) if pointer else b'')
        key = (pointer, rotation)
        if key not in rotated:
            rotated[key] = samples[pointer][ROTATION_INDEX[rotation]].reshape(23, 23)
        x, y = (index % columns) * 23, (index // columns) * 23
        result[y:y + 23, x:x + 23] = rotated[key] + base
    result.flags.writeable = False
    return result


def terrain_grid_point(heights, point):
    if heights is None:
        return point
    x, y = point
    iy, ix = min(max(int(y), 0), heights.shape[0] - 1), min(max(int(x), 0), heights.shape[1] - 1)
    shift = float(heights[iy, ix]) * HEIGHT_UNIT * WORLD_TO_GRID / 2
    return x - shift, y - shift


def height_correct_outline(rows, heights):
    """Project sparse edge texels into height-corrected grid space."""
    mask = np.frombuffer(b''.join(rows), dtype=np.uint8).reshape(len(rows), len(rows[0]))
    if heights is None:
        return mask * 255, (0, 0)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return mask.copy(), (0, 0)
    shift = -heights[ys, xs].astype(np.float32) * HEIGHT_UNIT * WORLD_TO_GRID / 2
    target_x, target_y = xs + shift, ys + shift
    origin_x, origin_y = int(np.floor(target_x.min())), int(np.floor(target_y.min()))
    width = int(np.ceil(target_x.max())) - origin_x + 2
    height = int(np.ceil(target_y.max())) - origin_y + 2
    if width * height > 64_000_000:
        raise ValueError('Height-corrected terrain image exceeds limit')
    output = np.zeros((height, width), dtype=np.uint8)
    fx, fy = target_x - origin_x, target_y - origin_y
    ix, iy = np.floor(fx).astype(np.int32), np.floor(fy).astype(np.int32)
    dx, dy = fx - ix, fy - iy
    for ox, oy, weights in ((0, 0, (1 - dx) * (1 - dy)), (1, 0, dx * (1 - dy)),
                            (0, 1, (1 - dx) * dy), (1, 1, dx * dy)):
        np.maximum.at(output, (iy + oy, ix + ox), np.rint(weights * 255).astype(np.uint8))
    return output, (origin_x, origin_y)
