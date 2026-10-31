"""Short display-only grace for missed reads; never makes stale data fresh."""
import time

class PresentationCache:
    def __init__(self,grace=.6):
        self.grace=grace;self.frame=None

    def resolve(self,snapshot,marks,key,foreground,now=None):
        now=time.monotonic()if now is None else now
        if not foreground or snapshot.source=='live'and(not snapshot.in_game or snapshot.loading):
            self.frame=None;return marks
        if snapshot.source=='live'and 0<=now-snapshot.captured_at<=.3:
            self.frame=(snapshot.captured_at,key,marks);return marks
        if snapshot.source=='disconnected'and self.frame:
            captured,previous,frame=self.frame
            if key==previous and 0<=now-captured<=self.grace:return frame
        self.frame=None;return marks
