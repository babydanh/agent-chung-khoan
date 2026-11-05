import json,sys
j=json.load(open("tree.json"))
steps=[];tops=[]  # tops: (id,name,group)
nid=[1]
def nxt():
    nid[0]+=1; return nid[0]
def color(hex_,a=1.0):
    if a is None or a>=0.999: return hex_
    return hex_+format(round(a*255),"02x")
def find(n,name):
    if n.get("name")==name: return n
    for c in n.get("kids",[]):
        r=find(c,name)
        if r: return r
def emit(n,parent,px,py,auto_parent):
    x=n["x"]-px; y=n["y"]-py
    if n["k"]=="icon":
        if not n.get("icon"): return
        i=nxt()
        steps.append({"command":"node.create","params":{"type":"frame","name":n["name"],"x":x,"y":y,"width":n["w"],"height":n["h"],"parent":parent,"props":{"fill":"none","pluginData":{"icon":n["icon"],"color":n["color"]}}}})
        return
    if n["k"]=="text":
        props={"fontFamily":"Inter","fontStyle":n["fw"],"fontSize":n["fs"],"fill":color(n["color"],n["a"]),"textAlign":n["ta"],"textAutoResize":"height"}
        if n.get("lh"): props["lineHeight"]=n["lh"]
        if n.get("ls"): props["letterSpacing"]=n["ls"]
        if n.get("tnum"): props["features"]={"tnum":True}
        nxt()
        steps.append({"command":"node.create","params":{"type":"text","name":n["name"] or "text","text":n["text"],"x":x,"y":y,"width":max(n["w"],1),"height":max(n["h"],1),"parent":parent,"props":props}})
        return
    props={}
    props["fill"]=color(n["fill"],n.get("fa",1)) if n.get("fill") else "none"
    if n.get("stroke"): props["stroke"]=n["stroke"]; props["strokeWeight"]=n["sw"]; props["strokeAlign"]="inside"
    if n.get("radius"): props["cornerRadius"]=round(n["radius"],2)
    if n.get("opacity") is not None: props["opacity"]=n["opacity"]
    if n.get("clip"): props["clip"]=True
    if n.get("layout"):
        props.update({"layout":n["layout"],"gap":n["gap"],"padding":n["pad"],"mainAlign":n["main"],"crossAlign":n["cross"]})
        if n.get("wrap"): props["wrap"]=True
    steps.append({"command":"node.create","params":{"type":"frame","name":n["name"],"x":x,"y":y,"width":n["w"],"height":n["h"],"parent":parent,"props":props}})
    me=nid[0]+1; nid[0]=me
    # fix: the create above got id me
    for c in n.get("kids",[]):
        emit(c,me,n["x"],n["y"],bool(n.get("layout")))

def infer(n):
    for c in n.get("kids",[]): infer(c)
    if n["k"]!="frame" or n.get("layout") or len(n.get("kids",[]))<2: return
    ks=[k for k in n["kids"]]
    # vertical stack
    v=sorted(ks,key=lambda k:(k["y"],k["x"]))
    ok=all(v[i+1]["y"]>=v[i]["y"]+v[i]["h"]-0.6 for i in range(len(v)-1))
    xs={round(k["x"]) for k in v}
    if ok and len(xs)==1:
        gaps=[v[i+1]["y"]-(v[i]["y"]+v[i]["h"]) for i in range(len(v)-1)]
        if max(gaps)-min(gaps)<=1.5:
            n["kids"]=v; n["layout"]="vertical"; n["gap"]=round(sum(gaps)/len(gaps),2)
            n["pad"]=[max(v[0]["y"]-n["y"],0),0,0,max(v[0]["x"]-n["x"],0)]; n["main"]="min"; n["cross"]="min"; return
    h=sorted(ks,key=lambda k:(k["x"],k["y"]))
    ok=all(h[i+1]["x"]>=h[i]["x"]+h[i]["w"]-0.6 for i in range(len(h)-1))
    cy={round(k["y"]+k["h"]/2) for k in h}
    if ok and max(cy)-min(cy)<=2:
        gaps=[h[i+1]["x"]-(h[i]["x"]+h[i]["w"]) for i in range(len(h)-1)]
        if max(gaps)-min(gaps)<=1.5:
            n["kids"]=h; n["layout"]="horizontal"; n["gap"]=round(sum(gaps)/len(gaps),2)
            n["pad"]=[0,0,0,max(h[0]["x"]-n["x"],0)]; n["main"]="min"; n["cross"]="center"

col=0;row=0;lastg=None
X=0;Y=0;rowh=0
CHROME={"status-bar","camera-dot","gesture-indicator"}
for f in j["frames"]:
    dev=f["tree"]
    scr=find(dev,"fr-screen")
    tb=find(dev,"tb-dev")
    if scr:
        ox,oy,W,H=scr["x"],scr["y"],scr["w"],scr["h"]
        kids=[k for k in scr["kids"] if k["name"] not in CHROME]+[k for k in dev["kids"] if k["name"]!="fr-screen" and k["name"] not in CHROME]
        bg=scr.get("fill","#0f1214")
    else:
        root=tb or dev; ox,oy,W,H=root["x"],root["y"],root["w"],root["h"]; kids=root["kids"]; bg=root.get("fill","#0f1214")
    if lastg!=f["group"]:
        lastg=f["group"]; X=0; Y+=(rowh+120) if rowh else 0; rowh=0
    steps.append({"command":"node.create","params":{"type":"frame","name":f["group"][1:].strip()+" / "+f["name"],"x":X,"y":Y,"width":W,"height":H,"props":{"fill":bg,"clip":True}}})
    nid[0]+=1; tid=nid[0]
    for c in kids:
        infer(c)
        emit(c,tid,ox,oy,False)
    tops.append({"id":tid,"name":f["name"],"group":f["group"]})
    X+=W+80; rowh=max(rowh,H)
json.dump(steps,open("/data/home/figcraft-work/out/build.json","w"))
json.dump(tops,open("tops.json","w"))
print("steps",len(steps),"frames",len(tops),"last id",nid[0])
