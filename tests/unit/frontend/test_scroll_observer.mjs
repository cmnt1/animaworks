/**
 * Unit tests for server/static/shared/chat/scroll-observer.js
 *
 * Run with: node --test tests/unit/frontend/test_scroll_observer.mjs
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import { createScrollObserver } from "../../../server/static/shared/chat/scroll-observer.js";

let lastObserver = null;

class MockIntersectionObserver {
  constructor(callback, options) {
    this.callback = callback;
    this.options = options;
    this.observed = new Set();
    this.unobserved = [];
    this.disconnected = false;
    lastObserver = this;
  }

  observe(target) {
    this.observed.add(target);
  }

  unobserve(target) {
    this.observed.delete(target);
    this.unobserved.push(target);
  }

  disconnect() {
    this.observed.clear();
    this.disconnected = true;
  }

  trigger(target, isIntersecting) {
    this.callback([{ target, isIntersecting }]);
  }
}

function flushTimers() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

function createScrollableContainer(sentinel) {
  const listeners = new Map();
  const container = {
    scrollTop: 120,
    querySelector: () => sentinel,
    getBoundingClientRect: () => ({ top: 0, bottom: 500 }),
    addEventListener: (type, callback) => {
      listeners.set(type, callback);
    },
    removeEventListener: (type, callback) => {
      if (listeners.get(type) === callback) listeners.delete(type);
    },
    dispatchScroll() {
      listeners.get("scroll")?.();
    },
    dispatchWheel(deltaY) {
      listeners.get("wheel")?.({ deltaY });
    },
    dispatchTouchStart(clientY) {
      listeners.get("touchstart")?.({ touches: [{ clientY }] });
    },
    dispatchTouchMove(clientY) {
      listeners.get("touchmove")?.({ touches: [{ clientY }] });
    },
    dispatchTouchEnd() {
      listeners.get("touchend")?.();
    },
  };
  return container;
}

describe("createScrollObserver", () => {
  beforeEach(() => {
    lastObserver = null;
    globalThis.IntersectionObserver = MockIntersectionObserver;
    globalThis.requestAnimationFrame = callback => setTimeout(callback, 0);
    globalThis.console.error = () => {};
  });

  it("does not repeatedly load while the sentinel remains visible", async () => {
    const sentinel = { id: "sentinel" };
    const container = { querySelector: () => sentinel };
    let calls = 0;

    const scrollObserver = createScrollObserver({
      container,
      onLoadMore: async () => {
        calls += 1;
      },
    });

    scrollObserver.observe();
    assert.ok(lastObserver.observed.has(sentinel));

    lastObserver.trigger(sentinel, true);
    await flushTimers();
    await flushTimers();
    assert.equal(calls, 1);

    lastObserver.trigger(sentinel, true);
    await flushTimers();
    assert.equal(calls, 1);

    lastObserver.trigger(sentinel, false);
    lastObserver.trigger(sentinel, true);
    await flushTimers();
    assert.equal(calls, 2);
  });

  it("ignores stale sentinel entries after refresh observes a replacement", async () => {
    const oldSentinel = { id: "old" };
    const newSentinel = { id: "new" };
    let currentSentinel = oldSentinel;
    const container = { querySelector: () => currentSentinel };
    let calls = 0;

    const scrollObserver = createScrollObserver({
      container,
      onLoadMore: async () => {
        calls += 1;
      },
    });

    scrollObserver.observe();
    currentSentinel = newSentinel;
    scrollObserver.refresh();

    lastObserver.trigger(oldSentinel, true);
    await flushTimers();
    assert.equal(calls, 0);

    lastObserver.trigger(newSentinel, true);
    await flushTimers();
    assert.equal(calls, 1);
  });

  it("loads again when the user scrolls upward into a still-visible sentinel", async () => {
    const sentinel = {
      id: "sentinel",
      getBoundingClientRect: () => ({ top: 10, bottom: 11 }),
    };
    const container = createScrollableContainer(sentinel);
    let calls = 0;

    const scrollObserver = createScrollObserver({
      container,
      onLoadMore: async () => {
        calls += 1;
      },
    });

    scrollObserver.observe();
    lastObserver.trigger(sentinel, true);
    await flushTimers();
    await flushTimers();
    assert.equal(calls, 1);

    lastObserver.trigger(sentinel, true);
    await flushTimers();
    assert.equal(calls, 1);

    container.scrollTop = 80;
    container.dispatchScroll();
    await flushTimers();
    await flushTimers();
    assert.equal(calls, 2);
  });

  it("loads on upward wheel intent when content cannot scroll", async () => {
    const sentinel = {
      id: "sentinel",
      getBoundingClientRect: () => ({ top: 8, bottom: 9 }),
    };
    const container = createScrollableContainer(sentinel);
    container.scrollTop = 0;
    let calls = 0;

    const scrollObserver = createScrollObserver({
      container,
      onLoadMore: async () => {
        calls += 1;
      },
    });

    scrollObserver.observe();
    lastObserver.trigger(sentinel, true);
    await flushTimers();
    await flushTimers();
    assert.equal(calls, 1);

    container.dispatchWheel(-80);
    await flushTimers();
    await flushTimers();
    assert.equal(calls, 2);

    container.dispatchWheel(-80);
    await flushTimers();
    assert.equal(calls, 2);
  });

  it("loads on downward touch drag intent when content cannot scroll", async () => {
    const sentinel = {
      id: "sentinel",
      getBoundingClientRect: () => ({ top: 8, bottom: 9 }),
    };
    const container = createScrollableContainer(sentinel);
    container.scrollTop = 0;
    let calls = 0;

    const scrollObserver = createScrollObserver({
      container,
      onLoadMore: async () => {
        calls += 1;
      },
    });

    scrollObserver.observe();
    container.dispatchTouchStart(20);
    container.dispatchTouchMove(32);
    await flushTimers();
    assert.equal(calls, 0);

    container.dispatchTouchMove(58);
    await flushTimers();
    await flushTimers();
    assert.equal(calls, 1);

    container.dispatchTouchMove(100);
    await flushTimers();
    assert.equal(calls, 1);

    container.dispatchTouchEnd();
    container.dispatchTouchStart(20);
    container.dispatchTouchMove(58);
    await flushTimers();
    await flushTimers();
    assert.equal(calls, 2);
  });
});
