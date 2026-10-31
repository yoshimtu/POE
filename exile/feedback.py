"""Local, explicit assessment feedback. Never changes the scoring model."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json

from exile.storage import read_json,write_json
from exile.rare_scoring import SCORER_VERSION,BASE,PROFILES
from exile.items import RULES

FEEDBACK_LABELS={'higher':'Should score higher','lower':'Should score lower','correct':'Looks right','archetype':'Build archetype selected'}


def model_signature():
    profiles={name:[sorted(core),sorted(anchors),weights]for name,(core,anchors,weights)in PROFILES.items()}
    content=json.dumps(dict(version=SCORER_VERSION,rules=RULES,weights=BASE,profiles=profiles),sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class FeedbackHistory:
    def __init__(self,path):
        self.path=path
        saved=read_json(path,{})
        self.examples=saved.get('examples',[])if isinstance(saved,dict)else[]
        self.examples=[entry for entry in self.examples if isinstance(entry,dict)and entry.get('feedback')in FEEDBACK_LABELS]

    def save(self):
        write_json(self.path,dict(schema_version=1,examples=self.examples))

    def record(self,context,direction,league='',area=''):
        if direction not in FEEDBACK_LABELS:raise ValueError('Unknown assessment feedback')
        item=asdict(context['item']);rating=deepcopy(context['rating'])
        signature=model_signature()
        identity=json.dumps(dict(item=item,preference=context['preference'],league=league,model=signature),sort_keys=True)
        identity=hashlib.sha256(identity.encode()).hexdigest()[:24]
        previous=next((e for e in self.examples if e['id']==identity),None)
        now=datetime.now(timezone.utc).isoformat(timespec='seconds')
        example=dict(id=identity,created_at=previous['created_at']if previous else now,updated_at=now,
            feedback=direction,note=previous.get('note','')if previous else'',
            scorer_version=SCORER_VERSION,model_signature=signature,
            league=league,area=area,source=context.get('source','hover'),
            build_preference=context['preference'],item=item,rating=rating,
            metadata=context.get('metadata',''),tooltip_rows=list(context.get('tooltip_rows',())))
        replacement=[e for e in self.examples if e['id']!=identity]+[example]
        # Save before publishing success to the UI, including vote replacements.
        write_json(self.path,dict(schema_version=1,examples=replacement))
        self.examples=replacement
        return example

    def set_note(self,identity,note):
        for example in self.examples:
            if example['id']==identity:
                previous=example.get('note','');example['note']=note
                try:self.save()
                except Exception:example['note']=previous;raise
                return

    def export(self,identities=None):
        selected=set(identities)if identities is not None else None
        examples=[e for e in reversed(self.examples)if selected is None or e['id']in selected]
        return json.dumps(dict(format='Waymark assessment feedback',schema_version=1,
            directions={'higher':'User thinks the displayed affix score should be higher',
                        'lower':'User thinks the displayed affix score should be lower',
                        'correct':'User thinks the displayed score looks right',
                        'archetype':'User selected this build archetype for the item'},
            examples=examples),ensure_ascii=False,indent=2)

    def delete(self,identities):
        selected=set(identities);replacement=[e for e in self.examples if e['id']not in selected]
        write_json(self.path,dict(schema_version=1,examples=replacement))
        self.examples=replacement
