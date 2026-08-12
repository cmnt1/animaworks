export class SpriteSheet {
  constructor(definition) {
    this.image = definition.image;
    this.frameW = definition.frameW || 64;
    this.frameH = definition.frameH || 64;
    this.anims = definition.anims || {};
    this.animation = "idle";
    this.elapsed = 0;
    this.frame = 0;
    this.flipped = false;
  }

  setAnimation(name, flipped = false) {
    const next = this.anims[name] ? name : "idle";
    if (next !== this.animation) {
      this.animation = next;
      this.elapsed = 0;
      this.frame = 0;
    }
    this.flipped = Boolean(flipped);
  }

  update(deltaSeconds) {
    const anim = this.anims[this.animation] || { frames: 1, fps: 1 };
    const frames = Math.max(1, anim.frames || 1);
    const fps = Math.max(0, anim.fps ?? 1);
    if (!fps) return;
    this.elapsed += deltaSeconds;
    this.frame = Math.floor(this.elapsed * fps) % frames;
  }

  draw(ctx, footX, footY, scale = 1) {
    if (!this.image) return false;
    const anim = this.anims[this.animation] || this.anims.idle || { row: 0 };
    const sourceX = this.frame * this.frameW;
    const sourceY = (anim.row || 0) * this.frameH;
    const width = this.frameW * scale;
    const height = this.frameH * scale;
    ctx.save();
    ctx.translate(Math.round(footX), Math.round(footY));
    if (this.flipped) ctx.scale(-1, 1);
    ctx.drawImage(
      this.image,
      sourceX,
      sourceY,
      this.frameW,
      this.frameH,
      Math.round(-width / 2),
      Math.round(-height),
      width,
      height,
    );
    ctx.restore();
    return true;
  }
}
