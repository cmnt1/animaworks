// Source-rectangle extraction only; original images are never edited.
export function atlasRects(image, columns = 4, rows = 2) {
  const canvas = document.createElement('canvas');
  canvas.width = image.width; canvas.height = image.height;
  const ctx = canvas.getContext('2d', { willReadFrequently:true });
  ctx.drawImage(image, 0, 0);
  const rects = [];
  for (let row = 0; row < rows; row++) for (let col = 0; col < columns; col++) {
    const x = Math.round(col * canvas.width / columns), y = Math.round(row * canvas.height / rows);
    const w = Math.round((col + 1) * canvas.width / columns) - x;
    const h = Math.round((row + 1) * canvas.height / rows) - y;
    const pixels = ctx.getImageData(x,y,w,h).data;
    let left=w, top=h, right=0, bottom=0;
    for (let py=0; py<h; py++) for (let px=0; px<w; px++) {
      if (pixels[(py*w+px)*4+3] < 40) continue;
      left=Math.min(left,px); top=Math.min(top,py); right=Math.max(right,px); bottom=Math.max(bottom,py);
    }
    rects.push({ x:x+left, y:y+top, w:right-left+1, h:bottom-top+1 });
  }
  return rects;
}
export const loadImage = src => new Promise((resolve,reject) => {
  const img = new Image(); img.onload=()=>resolve(img); img.onerror=()=>reject(new Error(`Asset unavailable: ${src}`)); img.src=src;
});

// Generated poses can extend beyond an exact grid cell. Find their alpha islands
// instead, so a thrusting weapon or a jumping character never gets clipped.
export function poseRegions(pixels, width, height) {
  const labels = new Int32Array(width * height), stack = new Int32Array(labels.length);
  const components = [];
  for (let start = 0; start < labels.length; start++) {
    if (labels[start] || pixels[start * 4 + 3] < 64) continue;
    const id = components.length + 1;
    const part = { id, count:0, left:width, top:height, right:0, bottom:0 };
    let length = 1; stack[0] = start; labels[start] = id;
    while (length) {
      const index = stack[--length], x = index % width, y = Math.floor(index / width);
      part.count++; part.left = Math.min(part.left,x); part.top = Math.min(part.top,y);
      part.right = Math.max(part.right,x); part.bottom = Math.max(part.bottom,y);
      const visit = next => {
        if (!labels[next] && pixels[next * 4 + 3] >= 64) { labels[next] = id; stack[length++] = next; }
      };
      if (x) visit(index-1); if (x+1<width) visit(index+1);
      if (y) visit(index-width); if (y+1<height) visit(index+width);
    }
    components.push(part);
  }
  const bodies = [...components].sort((a,b) => b.count-a.count).slice(0,8);
  if (bodies.length !== 8 || bodies.some(b => b.count < width*height*.005)) throw new Error('Battle sheet needs eight separate poses');
  bodies.sort((a,b) => (a.top+a.bottom)-(b.top+b.bottom));
  const poses = [bodies.slice(0,4),bodies.slice(4)].flatMap(row => row.sort((a,b) => (a.left+a.right)-(b.left+b.right)));
  const assignments = new Map(poses.map((part,index) => [part.id,index]));
  // Small, detached stars and spell particles travel with their nearest pose.
  for (const part of components) {
    if (assignments.has(part.id) || part.count < 20) continue;
    const x = (part.left+part.right)/2, y = (part.top+part.bottom)/2;
    const nearest = poses.map((body,index) => ({ index, distance:Math.hypot(Math.max(body.left-x,0,x-body.right),Math.max(body.top-y,0,y-body.bottom)) }))
      .sort((a,b) => a.distance-b.distance)[0];
    if (nearest.distance < Math.min(width,height)*.05) assignments.set(part.id,nearest.index);
  }
  const rects = poses.map(body => ({...body}));
  for (const part of components) {
    const index = assignments.get(part.id);
    if (index === undefined) continue;
    const rect = rects[index];
    rect.left = Math.min(rect.left,part.left); rect.top = Math.min(rect.top,part.top);
    rect.right = Math.max(rect.right,part.right); rect.bottom = Math.max(rect.bottom,part.bottom);
  }
  return { labels, assignments, rects:rects.map(r => ({x:r.left,y:r.top,w:r.right-r.left+1,h:r.bottom-r.top+1})) };
}

export function battleSheet(image) {
  const canvas = document.createElement('canvas');
  canvas.width = image.width; canvas.height = image.height;
  const ctx = canvas.getContext('2d', { willReadFrequently:true });
  ctx.drawImage(image,0,0);
  const source = ctx.getImageData(0,0,image.width,image.height);
  const { labels, assignments, rects } = poseRegions(source.data,image.width,image.height);
  // Decode each pose once into an in-memory texture. Source PNGs stay untouched.
  return rects.map((rect,pose) => {
    const texture = document.createElement('canvas'); texture.width = rect.w; texture.height = rect.h;
    const context = texture.getContext('2d'), data = context.createImageData(rect.w,rect.h);
    for (let y=0;y<rect.h;y++) for (let x=0;x<rect.w;x++) {
      const index = (rect.y+y)*image.width+rect.x+x;
      if (assignments.get(labels[index]) !== pose) continue;
      const to = (y*rect.w+x)*4, from = index*4;
      data.data.set(source.data.subarray(from,from+4),to);
    }
    context.putImageData(data,0,0);
    return { image:texture, rect:{x:0,y:0,w:rect.w,h:rect.h} };
  });
}
