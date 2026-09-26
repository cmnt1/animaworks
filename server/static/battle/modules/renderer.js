import { phaseAt, progressAt, monsterName, skillColor } from './combat.js';
import { atlasRects, battleSheet, loadImage } from './sheets.js';
export { phaseAt } from './combat.js';
const ENEMIES = [{x:175,y:345},{x:350,y:305},{x:525,y:380}];
const HEROES = [{x:708,y:258},{x:747,y:302},{x:786,y:346},{x:825,y:390}];
const lerp=(a,b,p)=>a+(b-a)*p;
const bell=p=>Math.sin(Math.PI*p);

export class BattleRenderer {
  constructor(canvas,model,t) {
    this.canvas=canvas; this.ctx=canvas.getContext('2d'); this.model=model; this.t=t;
    this.runtime=new Map(); this.page=0;
    this.reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  async load() {
    [this.background,this.atlas]=await Promise.all([
      loadImage(new URL('../assets/moonlit-ruins.png',import.meta.url)),
      loadImage(new URL('../assets/combatants.png',import.meta.url)), document.fonts.load('16px Pixel'),
    ]);
    this.rects=atlasRects(this.atlas);
  }
  async loadActors(names,basePath) {
    await Promise.allSettled(names.filter(name=>!this.runtime.has(name)).map(async name=>{
      this.runtime.set(name,null);
      try {
        const image=await loadImage(`${basePath}/api/animas/${encodeURIComponent(name)}/assets/battle_sheet_v1.png`);
        this.runtime.set(name,battleSheet(image));
      } catch { /* The generated job sprites cover Animas without battle art. */ }
    }));
  }
  visible(action) {
    const actors=[...this.model.actors.values()];
    const activeIndex=actors.findIndex(a=>a.name===action?.actor);
    if(activeIndex>=0) this.page=Math.floor(activeIndex/4);
    this.page%=Math.max(1,Math.ceil(actors.length/4));
    const party=actors.slice(this.page*4,this.page*4+4);
    // Active work takes the field before old queued/failed tasks.
    const tasks=[...this.model.tasks.values()].sort((a,b)=>Number(b.status==='in_progress')-Number(a.status==='in_progress'));
    const target=tasks.find(t=>t.key===action?.target), enemies=tasks.slice(0,3);
    if(target&&!enemies.includes(target)) enemies[2]=target;
    return {party,enemies,totalActors:actors.length,totalTasks:tasks.length};
  }
  text(text,x,y,color='#eef2df',size=14,align='center') {
    const c=this.ctx; c.font=`${size}px Pixel, monospace`; c.textAlign=align;
    c.fillStyle='#081323';c.fillText(text,Math.round(x+2),Math.round(y+2));
    c.fillStyle=color;c.fillText(text,Math.round(x),Math.round(y));
  }
  sprite(image,r,x,y,height,{alpha=1,tilt=0,squash=1,glow=false}={}) {
    if(!r||r.w<=0||r.h<=0) return;
    const c=this.ctx, w=Math.round(height*r.w/r.h);
    c.save();c.translate(Math.round(x),Math.round(y));c.rotate(tilt);c.scale(1/squash,squash);c.globalAlpha=alpha;
    if(glow){c.shadowColor='#ffdfa0';c.shadowBlur=8;}
    c.drawImage(image,r.x,r.y,r.w,r.h,-Math.round(w/2),-height,w,height);c.restore();
  }
  heroPose(action,phase,p,selected,victim) {
    if(victim&&phase==='damage') return action.blocked?1:6;
    if(!selected||action.side==='enemy') return 0;
    if(phase==='message'&&action.finish) return 7;
    if(action.command==='guard') return 1;
    if(phase==='cast') return 2;
    if(phase==='attack') return action.skill==='skyfall'?5:['rush','chain'].includes(action.skill)?4:action.command==='strike'?3:2;
    return 0;
  }
  draw(now,action,elapsed=0,damage=0) {
    const c=this.ctx,phase=action?phaseAt(elapsed,action):'idle';
    const p=action&&phase!=='done'?progressAt(elapsed,action,phase):0;
    const {party,enemies}=this.visible(action), enemyTurn=action?.side==='enemy';
    const ei=enemies.findIndex(t=>t.key===action?.target), ai=party.findIndex(a=>a.name===action?.actor);
    const ep=ENEMIES[ei],ap=HEROES[ai];
    c.imageSmoothingEnabled=false;c.clearRect(0,0,960,440);c.save();
    if(!this.reduced&&phase==='damage'&&['quake','meteor','skyfall','rockfall'].includes(action?.skill)) c.translate(Math.round(Math.sin(p*52)*4*(1-p)),Math.round(Math.cos(p*35)*2*(1-p)));
    c.drawImage(this.background,0,0,960,500);
    c.fillStyle=enemyTurn&&phase==='cast'?'#180e304c':'#04112022';c.fillRect(0,0,960,440);
    if(!this.reduced) for(let i=0;i<16;i++){c.fillStyle=i%3?'#9cdcc755':'#f1d99d99';c.fillRect((i*131+now*4)%960,65+i*71%330+Math.sin(now+i)*4,2,2);}
    enemies.forEach((enemy,i)=>{
      const pos=ENEMIES[i],selected=action?.target===enemy.key;
      const dying=selected&&!enemyTurn&&action.finish&&['damage','message'].includes(phase);
      const retreat=selected&&action.retreat&&['damage','message'].includes(phase);
      const fade=phase==='message'?0:1-p;
      let x=pos.x,y=pos.y,tilt=0,squash=1;
      if(!this.reduced){
        y+=Math.sin(now*2+i)* (enemy.sprite===1?5:1);
        if(selected&&enemyTurn){
          if(phase==='cast'){squash=1-.07*Math.sin(p*Math.PI*3);x+=Math.sin(p*30)*2;}
          if(phase==='attack'){
            if(['bounce','dive'].includes(action.skill)){x=lerp(pos.x,ap.x-30,bell(p));y-=bell(p)*(action.skill==='dive'?105:70);tilt=bell(p)*.15;}
            else if(action.skill==='quake'){y-=Math.max(0,Math.sin(p*Math.PI*2))*24;}
            else {x+=bell(p)*18;squash=1+bell(p)*.06;}
          }
        }else if(selected&&phase==='damage'&&!action.error){x+=Math.sin(p*48)*5*(1-p);}
      }
      c.fillStyle='#03111d66';c.beginPath();c.ellipse(pos.x,pos.y+3,42,8,0,0,Math.PI*2);c.fill();
      const h=[112,104,145,154][enemy.sprite];
      this.sprite(this.atlas,this.rects[enemy.sprite+4],x-(retreat?p*60:0),y,h,{alpha:dying||retreat?fade:1,tilt,squash,glow:selected&&enemyTurn&&phase==='cast'});
      if(!dying&&!retreat)this.text(monsterName(enemy,this.t),pos.x,pos.y+23,selected&&enemyTurn?'#ffb7ae':'#d9e9dd',11);
      if(selected&&['target','cast'].includes(phase))this.text(enemyTurn?'!':'▼',x,y-h-14,enemyTurn?'#ffad8a':'#fff2b6',21);
      if(dying&&!this.reduced)for(let j=0;j<18;j++){c.fillStyle=`rgba(239,218,153,${fade})`;c.fillRect(pos.x+Math.sin(j*8)*p*95,pos.y-h/2+Math.cos(j*5)*p*80,4,4);}
    });
    party.forEach((actor,i)=>{
      const pos=HEROES[i], selected=actor.name===action?.actor,victim=selected&&enemyTurn;
      let x=pos.x,y=pos.y,tilt=0;
      if(!this.reduced){
        y+=Math.round(Math.sin(now*2+i)*1.2);
        if(selected&&!enemyTurn){
          if(phase==='cast'){x-=16;y-=Math.sin(p*12)*2;}
          if(phase==='attack'){
            if(action.command==='strike'){
              const reach=action.skill==='rush'?pos.x-(ep?.x||400)-45:action.skill==='skyfall'?160:action.skill==='crosscut'?100:40;
              x-=bell(p)*reach;
              y-=action.skill==='skyfall'?bell(p)*110:action.skill==='rush'?Math.abs(Math.sin(p*22))*6:0;
              tilt=action.skill==='crosscut'?Math.sin(p*Math.PI*2)*.22:-bell(p)*.1;
            }else{x-=bell(p)*24;y-=action.skill==='stars'?bell(p)*14:0;}
          }
          if(phase==='message'&&action.finish)y-=Math.abs(Math.sin(p*9))*9;
        }
        if(victim&&phase==='damage'){x+=Math.sin(p*25)*9*(1-p)+bell(p)*12;tilt=bell(p)*.15;}
      }
      c.fillStyle='#020e1a77';c.beginPath();c.ellipse(x,pos.y+2,24,5,0,0,Math.PI*2);c.fill();
      const pose=this.heroPose(action,phase,p,selected,victim),sheet=this.runtime.get(actor.name);
      if(sheet){
        const frame=sheet[pose],r=frame.rect,height=Math.round(78*r.h/sheet[0].rect.h);
        this.sprite(frame.image,r,x,y,height,{tilt,glow:selected&&!enemyTurn&&action.limit,alpha:actor.state==='offline'?.5:1});
      }else this.sprite(this.atlas,this.rects[actor.sprite],x,y,77,{tilt,alpha:actor.state==='offline'?.5:1});
      this.text(actor.name,pos.x+46,pos.y-29,victim?'#ffafae':selected?'#ffedb2':'#c0d9df',12,'left');
      if(selected&&phase==='command')this.text(enemyTurn?'▼':'▶',x-48,y-44,enemyTurn?'#ffafae':'#fff5c6',19);
      if(actor.vital?.guard>0){c.strokeStyle='#a4cdf9';c.lineWidth=2;c.beginPath();c.arc(x,y-35,39,.65*Math.PI,1.65*Math.PI);c.stroke();}
      if(selected&&!enemyTurn&&phase==='cast')this.rune(x,y-6,skillColor(action),now,action.command==='guard'?42:30);
      if(actor.vital?.limit>=100)this.text(this.t('battle.limit_ready'),pos.x+46,pos.y-13,'#ffe09b',9,'left');
    });
    if(action&&ep&&ap){
      if(phase==='attack')this.effect(action,enemyTurn?ep:ap,enemyTurn?ap:ep,p);
      if(phase==='damage'){
        const pos=enemyTurn||action.recover?ap:ep, lift=this.reduced?0:bell(p)*24;
        const word=action.retreat?this.t('battle.retreat_number'):action.evaded?this.t('battle.evade'):action.error?this.t('battle.miss'):
          action.recover?'+'+action.healed:!enemyTurn&&action.command==='guard'?this.t('battle.guard_number'):String(damage);
        if(action.combo>1&&!enemyTurn&&!action.error&&!action.finish&&!action.recover&&damage>0){
          for(let j=0;j<3;j++)if(p>j*.12)this.text(String(Math.floor(damage/3)+(j===2?damage%3:0)),pos.x+(j-1)*28,pos.y-95-lift-j*12,skillColor(action),22);
          this.text(this.t('battle.combo',{count:3}),pos.x,pos.y-145,'#ffe4b1',12);
        }else this.text(word,pos.x,pos.y-88-lift,enemyTurn?'#ff8e9b':action.recover?'#8fffc5':skillColor(action),action.critical?34:29);
        if(action.critical&&!enemyTurn)this.text(this.t(action.limit?'battle.limit_break':'battle.critical'),pos.x,pos.y-132-lift,'#ffe5a0',14);
        if(enemyTurn&&action.blocked)this.text(this.t('battle.guard_number'),pos.x,pos.y-120-lift,'#a6ddff',12);
        if(!enemyTurn&&action.healed>0&&!action.recover){
          const ri=party.findIndex(a=>a.name===action.recipient);
          if(ri>=0)this.text('+'+action.healed,HEROES[ri].x,HEROES[ri].y-80-lift,'#8fffc5',21);
        }
      }
    }
    c.restore();
  }
  rune(x,y,color,now,radius){
    const c=this.ctx;c.strokeStyle=color;c.lineWidth=2;c.beginPath();c.ellipse(x,y,radius,10,0,0,Math.PI*2);c.stroke();
    if(!this.reduced)for(let j=0;j<8;j++){const a=now*4+j*Math.PI/4;c.fillStyle=color;c.fillRect(x+Math.cos(a)*radius,y-25+Math.sin(a)*20,3,3);}
  }
  effect(action,from,to,p){
    const c=this.ctx,color=skillColor(action),s=action.skill;
    c.save();c.strokeStyle=color;c.fillStyle=color;c.lineWidth=4;
    if(this.reduced){c.strokeRect(to.x-34,to.y-100,68,80);c.restore();return;}
    const tx=to.x,ty=to.y-65;
    const line=(points)=>{c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.stroke();};
    if(['crescent','crosscut','rush','skyfall','dive'].includes(s)){
      c.globalAlpha=bell(p);c.lineWidth=action.critical?7:4;
      if(s==='crescent'){c.beginPath();c.ellipse(tx,ty,60,45,-.6,-Math.PI/2,Math.PI/2);c.stroke();}
      else if(s==='skyfall'){line([[tx-12,50],[tx+4,ty+28]]);this.burst(tx,ty+24,p,color,12);}
      else for(let j=0;j<(s==='crosscut'?2:3);j++){const d=j%2?1:-1;line([[tx-46,ty-45*d+j*8],[tx+46,ty+45*d+j*8]]);}
    }else if(s==='flare'||s==='nightbolt'||s==='acid'){
      const x=lerp(from.x,tx,p),y=lerp(from.y-48,ty,p);
      for(let j=0;j<10;j++){c.globalAlpha=1-j/11;c.fillRect(x+(from.x>tx?1:-1)*j*7,y+Math.sin(j+p*15)*7,15-j,15-j);}
      if(p>.65)this.burst(tx,ty,(p-.65)/.35,color,14);
    }else if(s==='frost'){
      for(let j=0;j<6;j++){const x=tx-50+j*20,y=ty+35-bell(p)*70; c.beginPath();c.moveTo(x,y-30);c.lineTo(x+9,y);c.lineTo(x,y+20);c.lineTo(x-9,y);c.closePath();c.fill();}
    }else if(s==='thunder'){
      for(let j=0;j<3;j++){const x=tx+(j-1)*25;line([[x-20,70],[x+10,140],[x-7,175],[x+18,ty-20],[x,ty+25]]);}
    }else if(s==='meteor'||s==='rockfall'){
      for(let j=0;j<5;j++){const q=Math.min(1,Math.max(0,p*1.5-j*.12)),x=tx-55+j*25+70*(1-q),y=lerp(40,ty+25,q);c.globalAlpha=q<1?1:1-p;c.fillRect(x,y,17,17);line([[x+9,y-5],[x+28,y-35]]);}
    }else if(s==='breath'){
      const x=lerp(from.x,tx,p), y=lerp(from.y-70,ty,p);
      for(let j=0;j<22;j++){const f=j/22;c.fillStyle=j%2?'#ffb75f':'#f45c59';c.globalAlpha=1-f*.7;c.fillRect(lerp(from.x,x,f),lerp(from.y-70,y,f)+Math.sin(j*3+p*15)*f*48,12,12);}
    }else if(s==='quake'){
      for(let j=0;j<4;j++){c.beginPath();c.ellipse(tx,to.y+5,p*(40+j*24),6+j*4,0,0,Math.PI*2);c.stroke();}
      for(let j=0;j<7;j++)c.fillRect(tx-65+j*20,to.y-bell(p)*((j%3+1)*14),8,8);
    }else if(s==='gaze'){
      c.lineWidth=8*bell(p);line([[from.x,from.y-65],[tx,ty]]);c.lineWidth=2;c.strokeStyle='#ffcfef';line([[from.x,from.y-65],[tx,ty]]);this.burst(tx,ty,p,color,8);
    }else if(s==='bounce'){
      this.burst(tx,ty,p,color,10);
    }else if(['rally','heal','stars','chain'].includes(s)){
      if(s==='chain'){c.setLineDash([9,5]);line([[from.x,from.y-45],[tx,ty]]);}
      const center=action.recover||s==='heal'?from:to;
      for(let j=0;j<9;j++){const a=j*Math.PI*2/9+p*3,x=center.x+Math.cos(a)*45,y=center.y-50+Math.sin(a)*30-bell(p)*24;c.fillRect(x-5,y,14,4);c.fillRect(x,y-5,4,14);}
      this.rune(from.x,from.y-3,color,p*4,35+bell(p)*12);
    }else{
      const radius=28+bell(p)*24;c.lineWidth=s==='barrier'?5:2;
      c.beginPath();c.arc(from.x,from.y-40,radius,0,Math.PI*2);c.stroke();
      if(s==='parry')line([[from.x-45,from.y-60],[from.x+20,from.y-95]]);
      else this.burst(from.x,from.y-40,p,color,s==='focus'?6:12);
    }
    c.restore();
  }
  burst(x,y,p,color,count){
    const c=this.ctx;c.fillStyle=color;
    for(let j=0;j<count;j++){const a=j*Math.PI*2/count;c.globalAlpha=1-p;c.fillRect(x+Math.cos(a)*p*70,y+Math.sin(a)*p*55,5,5);}
    c.globalAlpha=1;
  }
}
