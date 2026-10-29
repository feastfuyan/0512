#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watermark_pdf.py — 页面转图片 + 满屏平铺 logo/文字水印 + 合成 PDF
用法: python3 watermark_pdf.py <input.pdf|docx> [-o out.pdf] [--logo logo.png]
      [--text "凌云智矿 · 内部文件 禁止转发"] [--opacity 40] [--dpi-scale 2]
流程: 每页渲染为图片(PIL) → 在图片上平铺水印 → 图片合成 PDF（水印不可通过文本层删除）
"""
import argparse, os, subprocess, sys, io

DEFAULT_TEXT = "凌云智矿 · 内部文件 禁止转载\nCONFIDENTIAL · DO NOT DISTRIBUTE"

def docx_to_pdf(src):
    exe=os.environ.get("SOFFICE")
    for c in filter(None,[exe,"soffice","/Applications/LibreOffice.app/Contents/MacOS/soffice"]):
        if c=="soffice" or os.path.exists(c) or subprocess.run(["which",c],capture_output=True).returncode==0:
            exe=c;break
    else:
        exe=None
    if not exe: sys.exit("docx转PDF需要LibreOffice(soffice)；请先转成PDF。")
    outdir=os.path.dirname(os.path.abspath(src))
    r=subprocess.run([exe,"--headless","--convert-to","pdf","--outdir",outdir,src],capture_output=True,text=True)
    pdf=os.path.splitext(src)[0]+".pdf"
    if r.returncode!=0 or not os.path.exists(pdf): sys.exit(f"docx转PDF失败: {r.stderr}")
    return pdf

def make_tile(text_img, logo_img, tile_w, tile_h, opacity, logo_opacity=None):
    """生成一个平铺单元：logo 在上、文字在下，斜角由整体旋转实现"""
    from PIL import Image
    tile=Image.new("RGBA",(tile_w,tile_h),(0,0,0,0))
    if logo_img:
        lo = logo_opacity if logo_opacity is not None else max(opacity,0.35)
        max_w,max_h=int(tile_w*0.85),int(tile_h*0.55)
        sc=min(max_w/logo_img.width,max_h/logo_img.height)
        lw,lh=max(1,int(logo_img.width*sc)),max(1,int(logo_img.height*sc))
        logo=logo_img.convert("RGBA").resize((lw,lh),Image.LANCZOS)
        a=logo.split()[3].point(lambda v:int(v*lo))
        logo.putalpha(a)
        tile.paste(logo,((tile_w-lw)//2,max(0,(tile_h-lh)//3)),logo)
    if text_img:
        tw=int(tile_w*1.4)
        th=int(tw*text_img.height/text_img.width)
        max_th=int(tile_h*0.28)              # 文字区最多占 tile 高度28%，保证两行完整
        if th>max_th:
            tw=int(tw*max_th/th); th=max_th
        txt=text_img.convert("RGBA").resize((tw,th))
        a=txt.split()[3].point(lambda v:int(v*opacity))
        txt.putalpha(a)
        ty=min(int(tile_h*0.72),tile_h-th-4) # 不超出 tile 底边
        tile.alpha_composite(txt,((tile_w-tw)//2,ty))
    return tile

def render_text_img(text, font_size=34):
    """用 fitz 把文字渲染成透明 PNG（多行，首行为主、次行辅助小字）"""
    import fitz
    lines=text.split("\n")
    d=fitz.open(); p=d.new_page(width=100,height=90)
    sizes=[font_size]+[int(font_size*0.62)]*(len(lines)-1)   # 次行约62%大小
    tw=max(fitz.get_text_length(l,fontname="china-s",fontsize=sz) for l,sz in zip(lines,sizes))
    gap=int(font_size*0.42)
    ph=int(sum(sz*1.45 for sz in sizes)+gap*(len(lines)-1))+30
    p=d.new_page(width=int(tw)+40,height=ph)
    y=50
    for l,sz in zip(lines,sizes):
        lw=fitz.get_text_length(l,fontname="china-s",fontsize=sz)
        p.insert_text(((int(tw)+40-lw)//2,y),l,fontsize=sz,fontname="china-s",
                      color=(0.42,0.42,0.42) if sz<font_size else (0.35,0.35,0.35))
        y+=int(sz*1.45+gap)
    pm=p.get_pixmap(clip=fitz.Rect(0,10,int(tw)+40,ph),alpha=True)
    from PIL import Image
    return Image.open(io.BytesIO(pm.tobytes("png")))

def watermark_page_image(img, logo_img, text_img, opacity):
    from PIL import Image
    W,H=img.size
    tile_w,tile_h=W//3,H//5
    tile=make_tile(text_img,logo_img,tile_w,int(tile_h*0.8),opacity)
    tile=tile.rotate(30,expand=True,resample=Image.BICUBIC)
    overlay=Image.new("RGBA",(W,H),(0,0,0,0))
    step_x,step_y=W//3,H//4
    row=0
    for y in range(-tile_h,H+tile_h,step_y):
        x0=(-tile_w//2 if row%2 else 0)
        for x in range(x0,W+tile_w,step_x):
            overlay.alpha_composite(tile,(x,y))
        row+=1
    base=img.convert("RGBA")
    base.alpha_composite(overlay)
    return base.convert("RGB")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o","--output")
    ap.add_argument("--logo",default=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","assets","lynai_mines_wordmark.png"))
    ap.add_argument("--text",default=DEFAULT_TEXT)
    ap.add_argument("--opacity",type=float,default=0.35,help="水印不透明度0-1")
    ap.add_argument("--dpi-scale",type=int,default=2,help="页面渲染倍率")
    args=ap.parse_args()
    from PIL import Image
    import fitz
    src=args.input
    if src.lower().endswith(".docx"): src=docx_to_pdf(src)
    doc=fitz.open(src)
    logo_img=Image.open(args.logo) if args.logo and os.path.exists(args.logo) else None
    if not logo_img: print("⚠️ 未找到logo，使用纯文字水印")
    text_img=render_text_img(args.text) if args.text else None
    out=fitz.open()
    for page in doc:
        pm=page.get_pixmap(matrix=fitz.Matrix(args.dpi_scale,args.dpi_scale))
        img=Image.open(io.BytesIO(pm.tobytes("png")))
        img=watermark_page_image(img,logo_img,text_img,args.opacity)
        buf=io.BytesIO(); img.save(buf,format="JPEG",quality=85)
        np=out.new_page(width=page.rect.width,height=page.rect.height)
        np.insert_image(page.rect,stream=buf.getvalue())
    dest=args.output or os.path.splitext(args.input)[0]+"_水印版.pdf"
    out.save(dest,garbage=4,deflate=True)
    print("saved:",dest)

if __name__=="__main__": main()
