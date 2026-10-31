"""Local compiled grid search. The library receives only our collision copy."""
import ctypes as c
from pathlib import Path
import sys

from exile.navigation import route as python_route

_library=None
_grid=None
_raw=None
_cancel_type=c.CFUNCTYPE(c.c_int)


def library():
    global _library
    if _library is None:
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        path=root/'native'/'route_search.dll'
        if sys.platform!='win32' or not path.is_file():return None
        dll=c.CDLL(str(path))
        dll.route_search.argtypes=[c.c_void_p,*([c.c_int]*6),c.c_uint,c.c_int,_cancel_type,
                                   c.POINTER(c.POINTER(c.c_int)),c.POINTER(c.c_int),c.POINTER(c.c_double)]
        dll.route_search.restype=c.c_int
        dll.route_free.argtypes=[c.POINTER(c.c_int)]
        dll.route_free.restype=None
        _library=dll
    return _library


def route(grid,start,goal,limit=100000,walk_values=None,cancel=None,stats=None):
    global _grid,_raw
    dll=library()
    if dll is None:return python_route(grid,start,goal,limit,walk_values,cancel,stats)
    if stats is not None:stats.update(status='invalid',visited=0,engine='native')
    if not grid or not grid[0]:return []
    width,height=len(grid[0]),len(grid)
    if width>8192 or height>8192 or width*height>32000000 or any(len(row)!=width for row in grid):return []
    if cancel is not None and cancel.is_set():
        if stats is not None:stats.update(status='cancelled')
        return []
    if _grid is not grid or any(not isinstance(row,bytes)for row in grid):
        _grid=grid;_raw=b''.join(bytes(row)for row in grid)
    mask=sum(1<<v for v in (range(1,32) if walk_values is None else set(walk_values)) if 0<=v<32)
    callback=_cancel_type(lambda:int(cancel.is_set()) if cancel is not None else 0)
    output=c.POINTER(c.c_int)();visited=c.c_int();cost=c.c_double()
    length=dll.route_search(c.c_char_p(_raw),width,height,*map(int,start),*map(int,goal),mask,int(limit),
                            callback,c.byref(output),c.byref(visited),c.byref(cost))
    status='ready' if length>0 else {0:'unreachable',-1:'invalid',-2:'limit',-3:'cancelled',-4:'allocation'}.get(length,'invalid')
    if stats is not None:
        stats.update(status=status,visited=visited.value)
        if length>0:stats['cost']=cost.value
    if length<=0:return []
    try:return [(output[i]%width,output[i]//width)for i in range(length)]
    finally:dll.route_free(output)
