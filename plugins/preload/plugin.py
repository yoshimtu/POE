import json
from pathlib import Path
import time

from exile.model import Mark, Plugin

CATALOG=json.loads(Path(__file__).with_name('catalog.json').read_text(encoding='utf-8'))['rules']
TITLES={'unique_boxes':'Unique strongboxes','special_essences':'Notable / special essences',
        'legion_generals':'Legion generals'}


def normalize(resource):
    return resource.replace('\\','/').split('@',1)[0].strip().casefold()


def bucket(resource):
    return '/'.join(resource.split('/')[:3])


class Preload(Plugin):
    id, name, category = "preload", "Instance preload alerts", "Awareness"
    description = "Common mechanics, valuable strongboxes and notable encounters. Preloads suggest content; Seen means observed in this instance."
    requires = {"preloads"}
    defaults = dict(overlay_size=[],overlay_position=[],overlay_locked=False,patterns='',limit=12,x=30,y=110,width=320,font_size=12,opacity=85,show_in_town=False)
    fields = {'limit':('Maximum alerts','int',1,30),'x':('Left position (pixels)','int',0,7680),
              'y':('Top position (pixels)','int',0,4320),'width':('Panel width (pixels)','int',240,600),
              'font_size':('Text size (pixels)','int',10,18),'opacity':('Background opacity %','int',20,100),
              'show_in_town':('Show in towns / hideout','bool'),
              'patterns':('Custom resource substrings, one per line (up to 128)','text')}
    settings_groups={'Mechanics':[],'Strongboxes':[],'Notables':[],
                     'Display':['limit','x','y','width','font_size','opacity','show_in_town','overlay_locked'],'Custom':['patterns']}
    for rule in CATALOG:
        key='show_'+rule['setting']
        if key not in defaults:
            defaults[key]=rule['default']
            fields[key]=(TITLES.get(rule['setting'],rule['label']),'bool')
            settings_groups[rule['group']].append(key)

    fields['overlay_locked']=('Lock overlay position and size (click through)','bool')

    def __init__(self):
        super().__init__()
        self.index={}
        for rule in CATALOG:
            for pattern in rule['patterns']:
                prefix=normalize(pattern)
                self.index.setdefault(bucket(prefix),[]).append((prefix,rule))
        self.stop()

    def stop(self):
        self.instance=None
        self.seen_resources=set()
        self.seen_raw_resources=set()
        self.alerts={}
        self.custom=None
        self.scan_at=0

    def matching_rules(self,resource):
        # Shared object templates are loaded even without their encounter.
        if resource.endswith(('.ot','.ot.tok')):return
        for prefix,rule in self.index.get(bucket(resource),()):
            if resource.startswith(prefix):
                # The generic box must not also classify a Divination/Scarab box.
                if rule['id']=='ordinary' and resource[len(prefix):] not in ('','.ao','.ao.tok','.ot','.ot.tok'):continue
                yield rule

    def detect(self,rule,resource,seen=False):
        entry=self.alerts.setdefault(rule['id'],dict(id=rule['id'],label=rule['label'],
                color=rule['color'],priority=rule['priority'],setting='show_'+rule['setting'],
                evidence='Preload',resources=[]))
        if seen:entry['evidence']='Seen'
        if resource not in entry['resources'] and len(entry['resources'])<3:entry['resources'].append(resource)

    def scan(self,snapshot,now):
        context=getattr(snapshot,'visual_context',None)
        instance=(snapshot.source,snapshot.area_id or snapshot.area,
                  tuple(context['key'][:6])if context else ())
        custom=tuple(p.strip().casefold()for p in self.settings['patterns'].splitlines()if p.strip())[:128]
        if instance!=self.instance or custom!=self.custom:
            self.stop();self.instance=instance;self.custom=custom
        if now<self.scan_at:return
        self.scan_at=now+.25
        for resource in snapshot.preloads:
            if resource in self.seen_raw_resources:continue
            self.seen_raw_resources.add(resource)
            normalized=normalize(resource)
            if normalized in self.seen_resources:continue
            self.seen_resources.add(normalized)
            for rule in self.matching_rules(normalized):self.detect(rule,resource)
            if any(pattern in normalized for pattern in custom):
                key='custom:'+normalized
                self.alerts[key]=dict(id=key,label=resource.rsplit('/',1)[-1],color='#aab7cb',
                    priority=8,setting=None,evidence='Preload',resources=[resource])
        # Observed entities strengthen evidence, but do not guess count/rarity
        # from the number of loaded files. Seen is instance history, not availability.
        for entity in snapshot.entities:
            if entity.get('used') is True:continue
            resource=entity.get('metadata')or''
            for rule in self.matching_rules(normalize(resource)):self.detect(rule,resource,seen=True)

    def alert_rows(self):
        return sorted((dict(alert)for alert in self.alerts.values()
            if not alert['setting'] or self.settings[alert['setting']]),
            key=lambda row:(row['priority'],row['label'].casefold()))

    def tick(self, snapshot, ctx):
        self.scan(snapshot,time.monotonic())
        if snapshot.town and not self.settings['show_in_town']:return []
        rows=self.alert_rows()
        if not rows:return []
        limit=self.settings['limit']
        return [Mark('preload_panel',self.settings['x'],self.settings['y'],
            payload=dict(rows=rows[:limit],overflow=max(0,len(rows)-limit),settings=dict(self.settings)))]


def create_plugin():
    return Preload()
