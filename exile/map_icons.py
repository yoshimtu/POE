"""Bundled map art, selected by native icon identity before category fallbacks."""
from functools import lru_cache
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
import numpy as np
import cv2
from exile.storage import resource_root,read_json

CATEGORY_ICONS={
 'waypoint':'Waypoint','exit':'Entrance','portal':'Portal','strongbox':'Strongbox',
 'shrine':'Shrine','quest':'QuestObject','recipe':'CraftingUnlockObject','chest':'RewardChestGeneric',
 'legion':'LegionInitiator','essence':'Essence','breach':'Breach','abyss':'Abyss',
 'ritual':'RitualRune','expedition':'ExpeditionDetonator','harvest':'HarvestPortal',
 'blight':'BlightCore','delirium':'AfflictionInitiator','delve':'DelveMineralVein',
 'heist':'HeistSumgglersCache','ultimatum':'UltimatumAltar','sanctum':'Sanctum',
 'harbinger':'RewardHarbinger','masters':'NPC','incursion':'EntrancePortal',
 'betrayal':'BetrayalSymbolCart','trial':'Labyrinth','encounter':'QuestObject',
}

@lru_cache(maxsize=1)
def catalog():
    return read_json(resource_root()/'plugins/radar/icon_catalog.json',{}).get('icons',{})


def icon_key(entity,category):
    if category in ('normal','magic','rare','unique'):
        return 'poe2:'+('UniqueMonsterAlive'if category=='unique'else'RareMonsterAlive')
    native=entity.get('native_icon','')
    if 'poe1:'+native in catalog():return 'poe1:'+native
    name=CATEGORY_ICONS.get(category,'')
    text=(entity.get('name','')+' '+entity.get('metadata','')).casefold()
    if category=='eldritch':name='TangleAltar'if any(k in text for k in ('tangle','eater'))else'CleansingFireAltar'
    elif category=='settlers':
        for needle,icon in (('verisium','Verisium'),('crimson','CrimsonIron'),('orichalcum','DemonCopper'),('bismuth','Bismuth'),('amber','PetrifiedWood'),('petrified','PetrifiedWood')):
            if needle in text:name='OreType'+icon;break
    elif category=='allflame':
        name='DeepwaterCursedTreasure'if 'cursedtreasure'in text.replace(' ','')else'BrinerotStores'if 'brinerot'in text else''
    key='poe1:'+name
    return key if key in catalog() else ''


@lru_cache(maxsize=256)
def original_image(key):
    entry=catalog().get(key)
    if not entry:return QImage()
    root=(resource_root()/'plugins/radar').resolve();path=(root/entry['file']).resolve()
    if not path.is_relative_to(root):return QImage()
    return QImage(str(path))


@lru_cache(maxsize=32)
def recolored_image(key,color):
    image=original_image(key)
    if image.isNull()or not color:return image
    target=QColor(color)
    if not target.isValid()or target.hsvHueF()<0:return image
    source=image.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels=np.frombuffer(source.constBits(),dtype=np.uint8).reshape(source.height(),source.bytesPerLine())
    rgba=pixels[:,:source.width()*4].reshape(source.height(),source.width(),4).copy()
    hsv=cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2HSV_FULL)
    # Hue alone changes; saturation, brightness and alpha remain the source's.
    hsv[:,:,0]=round(target.hsvHueF()*255)
    rgba[:,:,:3]=cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB_FULL)
    return QImage(rgba.data,source.width(),source.height(),rgba.strides[0],QImage.Format.Format_RGBA8888).copy()


@lru_cache(maxsize=128)
def icon_image(key,diameter,ratio=1.,tint=''):
    image=recolored_image(key,tint)if tint else original_image(key)
    if image.isNull():return image
    pixels=max(1,round(diameter*ratio))
    return image.scaled(pixels,pixels,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
