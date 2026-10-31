/* Bounded A* over an owned collision buffer. No game/process APIs or input. */
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
#include <float.h>

typedef struct { double f, g; int cell; } Entry;
typedef struct { Entry *items; size_t count, capacity; } Heap;
typedef int (*Cancel)(void);
#define API __declspec(dllexport)

static int less(Entry a, Entry b) {
    return a.f < b.f || (a.f == b.f && (a.g < b.g || (a.g == b.g && a.cell < b.cell)));
}
static int push(Heap *heap, Entry entry) {
    if (heap->count == heap->capacity) {
        size_t capacity = heap->capacity ? heap->capacity * 2 : 1024;
        if (capacity > 32000000) return 0;
        Entry *items = realloc(heap->items, capacity * sizeof(Entry));
        if (!items) return 0;
        heap->items = items; heap->capacity = capacity;
    }
    size_t index = heap->count++;
    while (index && less(entry, heap->items[(index-1)/2])) {
        heap->items[index] = heap->items[(index-1)/2]; index = (index-1)/2;
    }
    heap->items[index] = entry; return 1;
}
static Entry pop(Heap *heap) {
    Entry result = heap->items[0], last = heap->items[--heap->count];
    if (!heap->count) return result;
    size_t index = 0;
    while (index * 2 + 1 < heap->count) {
        size_t child = index * 2 + 1;
        if (child + 1 < heap->count && less(heap->items[child+1], heap->items[child])) child++;
        if (!less(heap->items[child], last)) break;
        heap->items[index] = heap->items[child]; index = child;
    }
    heap->items[index] = last; return result;
}
static double heuristic(int x, int y, int gx, int gy) {
    int dx=abs(x-gx), dy=abs(y-gy), small=dx<dy?dx:dy, large=dx>dy?dx:dy;
    return large + 0.4142135623730950488 * small;
}
static int walk(const uint8_t *grid, int width, int height, int x, int y, unsigned mask) {
    return x>=0 && y>=0 && x<width && y<height && grid[y*width+x]<32 && (mask & (1u<<grid[y*width+x]));
}
API void route_free(int *path) { free(path); }

/* Positive: path length; 0: unreachable; -1: invalid; -2: budget;
   -3: cancelled; -4: allocation failure. Output is owned by route_free. */
API int route_search(const uint8_t *grid, int width, int height,
    int sx, int sy, int gx, int gy, unsigned mask, int limit, Cancel cancel,
    int **output, int *visited, double *cost) {
    *output=NULL; *visited=0; *cost=0;
    if (!grid || width<=0 || height<=0 || width>8192 || height>8192 ||
        (int64_t)width*height>32000000 || limit<=0 ||
        !walk(grid,width,height,sx,sy,mask) || !walk(grid,width,height,gx,gy,mask)) return -1;
    size_t cells=(size_t)width*height;
    double *scores=malloc(cells*sizeof(double));
    int *parents=malloc(cells*sizeof(int));
    Heap heap={0}; int status=-4;
    if (!scores || !parents) goto cleanup;
    for (size_t i=0;i<cells;i++) { scores[i]=DBL_MAX; parents[i]=-1; }
    int start=sy*width+sx, goal=gy*width+gx;
    scores[start]=0;
    if (!push(&heap,(Entry){heuristic(sx,sy,gx,gy),0,start})) goto cleanup;
    while (heap.count && *visited<limit) {
        Entry current=pop(&heap);
        if (current.g!=scores[current.cell]) continue;
        ++*visited;
        if ((*visited & 2047)==0 && cancel && cancel()) { status=-3; goto cleanup; }
        if (current.cell==goal) {
            int length=1, cursor=goal;
            while (cursor!=start) {
                cursor=parents[cursor];
                if (cursor<0 || ++length>limit) { status=-1; goto cleanup; }
            }
            int *path=malloc((size_t)length*sizeof(int));
            if (!path) goto cleanup;
            cursor=goal;
            for (int i=length-1;i>=0;i--) { path[i]=cursor; cursor=parents[cursor]; }
            *output=path; *cost=current.g; status=length; goto cleanup;
        }
        int x=current.cell%width, y=current.cell/width;
        for (int dy=-1;dy<=1;dy++) for (int dx=-1;dx<=1;dx++) {
            if ((!dx && !dy) || !walk(grid,width,height,x+dx,y+dy,mask)) continue;
            if (dx && dy && (!walk(grid,width,height,x+dx,y,mask) || !walk(grid,width,height,x,y+dy,mask))) continue;
            int next=(y+dy)*width+x+dx;
            double score=current.g+(dx && dy ? 1.4142135623730950488 : 1.0);
            if (score<scores[next]) {
                scores[next]=score; parents[next]=current.cell;
                if (!push(&heap,(Entry){score+heuristic(x+dx,y+dy,gx,gy),score,next})) goto cleanup;
            }
        }
    }
    status=heap.count ? -2 : 0;
cleanup:
    free(heap.items); free(scores); free(parents); return status;
}
