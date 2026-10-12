# -*- coding: utf-8 -*-
"""裁剪联合bbox + 放大 + alpha二值化收紧边缘(清拖影) + 底部窄hue清残留"""
import os, sys
import cv2, numpy as np
from PIL import Image
sys.path.insert(0, r"C:\Users\13544\AppData\Roaming\WPS 灵犀\serverdir\target_skills\lingxi-pet\scripts")
from chroma_key_to_gif import rgba_to_gif_frames, DEFAULT_ALPHA_THRESHOLD
acts=["tianhe_shoot","lingsha_ziying","lingsha_tianhe","mengli_ziying","mengli_lingsha"]
HUES={"tianhe_shoot":(72,90),"lingsha_ziying":(28,50),"lingsha_tianhe":(42,60),
      "mengli_ziying":(71,87),"mengli_lingsha":(50,72)}
SRC=r"D:\TOOL\20260831-14-46-47-666\lingxi-pet\_build6"
DST=r"D:\TOOL\20260831-14-46-47-666\lingxi-pet\_build6_zoom"
os.makedirs(DST,exist_ok=True)
TARGET_W=0.85; TARGET_H=1.15; BOT=0.12; ALPHA_KEEP=190
def join_bbox(im,n):
    minx=miny=10**9;maxx=maxy=-1
    for i in range(n):
        im.seek(i); a=np.array(im.convert("RGBA"))[...,3]
        ys,xs=np.where(a>16)
        if len(xs)==0: continue
        minx=min(minx,xs.min());maxx=max(maxx,xs.max());miny=min(miny,ys.min());maxy=max(maxy,ys.max())
    return minx,miny,maxx+1,maxy+1
for a in acts:
    g=os.path.join(SRC,a,a+".gif")
    im=Image.open(g); n=im.n_frames; dur=im.info.get("duration",40)
    bx0,by0,bx1,by1=join_bbox(im,n); bw,bh=bx1-bx0,by1-by0
    scale=min(TARGET_W*720/bw,TARGET_H*720/bh); nw,nh=int(round(bw*scale)),int(round(bh*scale))
    hl,hh=HUES[a]; frames=[]
    for i in range(n):
        im.seek(i); arr=np.array(im.convert("RGBA"))
        crop=arr[by0:by1,bx0:bx1]
        pil=Image.fromarray(crop,"RGBA").resize((nw,nh),Image.LANCZOS); cxa=np.array(pil)
        canvas=np.zeros((720,720,4),np.uint8)
        x0=(720-nw)//2; y0=(720-nh)//2
        sx=max(0,x0); sy=max(0,y0); ex=min(720,x0+nw); ey=min(720,y0+nh)
        csx=max(0,-x0); csy=max(0,-y0)
        if ex>sx and ey>sy: canvas[sy:ey,sx:ex]=cxa[csy:csy+(ey-sy),csx:csx+(ex-sx)]
        # 底部带清残留
        bot_start=int(720*(1-BOT))
        hsv=cv2.cvtColor(canvas[...,:3],cv2.COLOR_RGB2HSV)
        m=cv2.inRange(hsv[bot_start:],(hl,25,30),(hh,255,255))
        k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
        m=cv2.morphologyEx(m,cv2.MORPH_OPEN,k,1)
        canvas[bot_start:][m>0,3]=0
        # alpha二值化收紧(清半透明拖影)
        al=canvas[...,3]
        canvas[...,3]=np.where(al>=ALPHA_KEEP,255,0).astype(np.uint8)
        frames.append(rgba_to_gif_frames(Image.fromarray(canvas,"RGBA"),DEFAULT_ALPHA_THRESHOLD))
    out=os.path.join(DST,a+".gif")
    frames[0].save(out,save_all=True,append_images=frames[1:],duration=dur,loop=0,transparency=0,disposal=2,optimize=False)
    print(f"{a}: scale={scale:.2f} 完成",flush=True)
print("全部完成")
