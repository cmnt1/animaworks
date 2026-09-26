import test from 'node:test';
import assert from 'node:assert/strict';
import { BattleModel } from '../../../server/static/battle/modules/model.js';
import { BattleCombat, SKILLS, monsterIdentity, monsterName, phaseAt, timings } from '../../../server/static/battle/modules/combat.js';
import { poseRegions } from '../../../server/static/battle/modules/sheets.js';
import { readFileSync } from 'node:fs';

function scene(random = () => .5) {
  const model = new BattleModel();
  model.roster([{name:'hero',status:'idle'}]);
  const task = model.task('hero','job',{title:'/work/tests/test_search.py',status:'in_progress',sprite:2});
  const combat = new BattleCombat(model,random);
  return { model, task, combat, hero:model.actors.get('hero'), party:()=>[...model.actors.values()], enemies:()=>[...model.tasks.values()] };
}

test('identical events vary techniques and avoid repeating the previous technique', () => {
  let seed=42;
  const random=()=>((seed=(seed*1664525+1013904223)>>>0)/2**32);
  const {combat}=scene(random);
  for (const command of Object.keys(SKILLS)) {
    const actions=Array.from({length:80},()=>combat.prepare({actor:'hero',target:'job',command}));
    assert.equal(new Set(actions.map(a=>a.skill)).size,4);
    assert(actions.slice(1).every((a,i)=>a.skill!==actions[i].skill));
    assert(new Set(actions.map(a=>a.roll)).size>1);
    assert(actions.some(a=>a.critical) || command==='guard');
    assert(new Set(actions.map(a=>a.pace)).size>1);
  }
});

test('monsters attack during event silence and damage only scene HP', () => {
  const {model,combat,task,hero,party,enemies}=scene();
  combat.tick(4);
  const attack=combat.next(party(),enemies());
  assert.equal(attack.side,'enemy');
  const damage=combat.apply(attack); combat.settle(attack);
  assert(damage>0); assert.equal(hero.vital.hp,1200-damage);
  assert.equal(task.hp,999); assert.equal(task.status,'in_progress'); assert.equal(model.cleared,0);
  const counter=combat.next(party(),enemies());
  assert.equal(counter.counter,true); assert.equal(counter.cosmetic,true);
  combat.apply(counter); combat.settle(counter);
  assert(task.hp<999); assert(task.hp>=1); assert.equal(model.cleared,0);
});

test('defense mitigates enemy damage and taking damage charges limit', () => {
  const {combat,task,hero}=scene();
  const attack=()=>combat.prepare({actor:'hero',target:task.key,side:'enemy'});
  const first=combat.apply(attack());
  combat.apply(combat.prepare({actor:'hero',target:task.key,command:'guard',cosmetic:true}));
  const blocked=attack(), second=combat.apply(blocked);
  assert.equal(blocked.blocked,true); assert(second<first/2); assert(hero.vital.limit>30);
  hero.vital.limit=100;
  const limit=combat.prepare({actor:'hero',target:task.key,command:'strike'});
  assert.equal(limit.limit,true); assert.equal(limit.critical,true); assert.equal(hero.vital.limit,0);
});

test('recovery restores a wounded actor and scene counters can never defeat tasks', () => {
  const {model,combat,task,hero,party,enemies}=scene();
  combat.vital(hero).hp=0;
  const recovery=combat.next(party(),enemies());
  assert.equal(recovery.recover,true);
  combat.apply(recovery); combat.settle(recovery);
  assert(hero.vital.hp>=500); assert.equal(task.hp,999);
  for(let i=0;i<100;i++) {
    const action=combat.prepare({actor:'hero',target:task.key,cosmetic:true,counter:true});
    combat.apply(action); combat.settle(action);
  }
  assert.equal(task.hp,1); assert.equal(model.cleared,0); assert.equal(task.status,'in_progress');
});

test('errors do not heal, guard, or damage; successful support heals', () => {
  const {combat,task,hero}=scene(); combat.vital(hero).hp=400;
  combat.apply(combat.prepare({actor:'hero',target:task.key,command:'support',error:true}));
  assert.equal(hero.vital.hp,400); assert.equal(task.hp,999);
  combat.apply(combat.prepare({actor:'hero',target:task.key,command:'support'}));
  assert(hero.vital.hp>400); assert(task.hp<999);
});

test('disconnect and absent opponents suppress ambient actions', () => {
  const {combat,hero,party,enemies}=scene(); combat.tick(30);
  assert.equal(combat.next(party(),enemies(),false),null);
  assert.equal(combat.next(party(),[]),null);
  hero.state='offline'; assert.equal(combat.next(party(),enemies()),null);
});

test('ambient combat cannot starve real task actions or alter completion counting', () => {
  const {model,combat,task,party,enemies}=scene();
  for(let i=0;i<10;i++) model.enqueue({actor:'hero',target:task.key,command:'magic'});
  model.terminal(task,'done','hero');
  for(let i=0;i<200 && model.tasks.size;i++) {
    combat.tick(.5);
    const action=combat.next(party(),enemies());
    if(!action)continue;
    combat.tick(timings(action).at(-1)); combat.apply(action); combat.settle(action);
  }
  assert.equal(model.cleared,1); assert.equal(model.tasks.size,0);
});

test('completion received during an enemy turn cancels its damage', () => {
  const {model,combat,task,hero,party,enemies}=scene(); combat.tick(4);
  const attack=combat.next(party(),enemies());
  model.terminal(task,'done','hero');
  assert.equal(combat.apply(attack),0); assert.equal(attack.evaded,true); assert.equal(combat.vital(hero).hp,1200);
  const finish=combat.next(party(),enemies()); combat.apply(finish); combat.settle(finish);
  assert.equal(model.cleared,1);
});

test('animation phase timings follow each technique pace', () => {
  assert.equal(phaseAt(.75,{pace:1}),'target');
  assert.equal(phaseAt(.75,{pace:2}),'command');
  assert.equal(phaseAt(10,{pace:2}),'done');
});

test('monster names are stable, semantic, localized, and never expose a path', () => {
  const {task}=scene();
  const identity=monsterIdentity(task); assert.equal(identity.theme,'storm');
  for(const locale of ['ja','en','ko']) {
    const strings=JSON.parse(readFileSync(new URL(`../../../server/static/i18n/${locale}.json`,import.meta.url)));
    const t=(key,params={})=>Object.entries(params).reduce((s,[k,v])=>s.replaceAll(`{${k}}`,v),strings[key]||key);
    const name=monsterName(task,t);
    assert(!name.includes('/')); assert(!name.includes('battle.')); assert(!name.includes('.py'));
    assert.equal(monsterName(task,t),name);
  }
  task.title='now a different title'; assert.deepEqual(monsterIdentity(task),identity);
});

test('alpha islands preserve eight poses that cross nominal atlas boundaries', () => {
  const width=160,height=120,pixels=new Uint8ClampedArray(width*height*4);
  const fill=(x,y,w,h)=>{for(let py=y;py<y+h;py++)for(let px=x;px<x+w;px++)pixels[(py*width+px)*4+3]=255;};
  for(let row=0;row<2;row++)for(let col=0;col<4;col++)fill(5+col*40,10+row*60,25,30);
  // First pose's weapon crosses x=40 below the adjacent pose, without touching it.
  fill(15,39,2,6); fill(15,44,36,2);
  const regions=poseRegions(pixels,width,height);
  assert.equal(regions.rects.length,8);
  assert.equal(regions.rects[0].x+regions.rects[0].w,51);
  assert.equal(regions.rects[1].w,25);
  assert.notEqual(regions.assignments.get(regions.labels[44*width+48]),regions.assignments.get(regions.labels[20*width+48]));
  assert.throws(()=>poseRegions(new Uint8ClampedArray(width*height*4),width,height),/eight/);
});
