"""Track an item only after it was read while the pointer was stationary."""
class HoverTracker:
    def __init__(self):
        self.position=None;self.stable_since=0.;self.item=None;self.area=None

    def sample(self,position,now,snapshot,foreground,preserve_missing=False):
        area=(snapshot.area_id,getattr(snapshot,'instance_key',None))
        if not foreground or snapshot.source!='live' or snapshot.loading:
            self.position=None;self.item=None;self.area=None;return
        if self.position is None or (position-self.position).manhattanLength()>8 or area!=self.area:
            self.position=position;self.stable_since=now;self.item=None;self.area=area
        item=snapshot.hovered_item
        if not item and not preserve_missing:self.item=None
        if item:
            captured=item.get('hover_captured_at',snapshot.captured_at)
            if captured>=self.stable_since and 0<=now-captured<=.35:
                self.item=dict(item)

    def current(self,position,now,snapshot,maximum_age=1.5):
        if self.item is None or self.position is None or (position-self.position).manhattanLength()>8:return None
        if self.area!=(snapshot.area_id,getattr(snapshot,'instance_key',None)):return None
        captured=self.item.get('hover_captured_at',0)
        return dict(self.item) if 0<=now-captured<=maximum_age else None
