"""Analyze saved timing/pose traces without attaching to the game."""
import bisect
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exile.native_map import map_translation
from tools.profile_map import stats


def trace_key(row):
    transform=row.get('raw')
    if not transform:return None
    return(row['area'],row['grid'],transform['mode'],tuple(transform['clip']),
           transform['basis_x'],transform['basis_y'])


def analyze(path):
    data = json.loads(Path(path).read_text())
    records = data['records']
    samples = defaultdict(dict)
    for row in records['motion']:
        if row['raw']:
            samples[trace_key(row)][row['captured']] = row['raw']
    groups = {key: sorted(value) for key, value in samples.items()}
    errors, sample_age, intervals, stops = [], [], [], []
    moving_frames, held_frames = 0, 0
    previous = None
    for row in records['motion']:
        key = trace_key(row)
        if not row['raw'] or key not in groups or row['t'] < 5:
            previous = None
            continue
        times = groups[key]
        target = row['t'] - 1/30
        i = bisect.bisect_right(times, target)
        if i == 0 or i == len(times):
            continue
        ta, tb = times[i-1:i+1]
        if tb-ta > .2:
            continue
        a, b = (map_translation(samples[key][t]) for t in (ta,tb))
        speed = math.dist(a,b)/(tb-ta)
        if speed > 5:
            moving_frames += 1
            alpha = (target-ta)/(tb-ta)
            ideal = tuple(x+(y-x)*alpha for x,y in zip(a,b))
            actual = map_translation(row['visual'])
            errors.append(math.dist(ideal,actual))
            sample_age.append(row['age']*1000)
            if previous and previous[0] == key and math.dist(previous[1],actual) < .01:
                held_frames += 1
        previous = key, map_translation(row['visual'])
    for key, times in groups.items():
        intervals.extend((b-a)*1000 for a,b in zip(times,times[1:]) if b-a < .3 and a>5)
        poses = [map_translation(samples[key][t]) for t in times]
        # Stationary position for >=100 ms after >5 px/s motion. Find when the
        # drawn pose first settles at that position and stays there for 50 ms.
        for i in range(1,len(times)-2):
            if times[i]-times[i-1] > .2 or math.dist(poses[i],poses[i-1]) < .05:
                continue
            j = i+1
            while j < len(times) and times[j]-times[i] < .3 and math.dist(poses[i],poses[j]) < .01:
                j += 1
            if times[j-1]-times[i] < .1:
                continue
            candidates = [r for r in records['motion'] if trace_key(r)==key
                          and times[i] <= r['t'] <= times[j-1] and r['visual']]
            for index,r in enumerate(candidates):
                later = [v for v in candidates[index:] if v['t'] <= r['t']+.05]
                if later and later[-1]['t']-r['t'] >= .035 and all(math.dist(map_translation(v['visual']),poses[i]) < .05 for v in later):
                    stops.append((r['t']-times[i])*1000)
                    break
    print(Path(path).name)
    print(json.dumps(dict(sample_interval_ms=stats(intervals), moving_sample_age_ms=stats(sample_age),
        moving_frames=moving_frames, held_moving_frames=held_frames,
        delayed_trajectory_error_pixels=stats(errors),stop_settle_ms=stats(stops)),indent=2))


if __name__ == '__main__':
    for path in sys.argv[1:]:
        analyze(path)
