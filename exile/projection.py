"""Shared world-to-client projection, without camera interpolation."""
import math


def project(matrix, point, width, height):
    if len(matrix) != 16 or len(point) != 3 or not all(math.isfinite(v) for v in (*matrix, *point)):
        return None
    p = (*point, 1.)
    clip = [sum(p[j] * matrix[j * 4 + i] for j in range(4)) for i in range(4)]
    if clip[3] <= .01:
        return None
    x = (1 + clip[0] / clip[3]) * width / 2
    y = (1 - clip[1] / clip[3]) * height / 2
    if not -200 <= x <= width + 200 or not -200 <= y <= height + 200:
        return None
    return (x, y)

