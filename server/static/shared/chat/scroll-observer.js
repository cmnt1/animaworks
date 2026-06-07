// ── Shared Scroll Observer ──────────────────────
// IntersectionObserver-based infinite scroll for chat history.

/**
 * Create a scroll observer for upward infinite scroll.
 * @param {object} config
 * @param {HTMLElement} config.container - The scrollable messages container
 * @param {string}   [config.sentinelSelector=".chat-load-sentinel"] - CSS selector for the sentinel element
 * @param {function}  config.onLoadMore - Called when sentinel becomes visible
 * @returns {{ observe: function, disconnect: function, refresh: function }}
 */
export function createScrollObserver(config) {
  const { container, onLoadMore, sentinelSelector = ".chat-load-sentinel" } = config;

  let observer = null;
  let observedSentinel = null;
  let loading = false;
  let armed = true;
  let lastScrollTop = 0;
  let removeScrollHandler = null;
  let removeIntentHandlers = null;
  let wheelGestureConsumed = false;
  let wheelGestureTimer = null;
  let touchStartY = null;
  let touchGestureConsumed = false;
  const LOAD_ROOT_MARGIN_TOP = 200;
  const WHEEL_GESTURE_RESET_MS = 400;
  const TOUCH_LOAD_THRESHOLD_PX = 24;

  function _schedule(fn) {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(fn);
    } else {
      setTimeout(fn, 0);
    }
  }

  function _isSentinelInLoadRange(sentinel) {
    if (!sentinel || !container) return false;
    if (typeof sentinel.getBoundingClientRect !== "function") return false;
    if (typeof container.getBoundingClientRect !== "function") return false;

    const sentinelRect = sentinel.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    return sentinelRect.bottom >= containerRect.top
      && sentinelRect.top <= containerRect.top + LOAD_ROOT_MARGIN_TOP;
  }

  function _loadFromSentinel(sentinel) {
    if (!armed || loading) return false;

    armed = false;
    loading = true;
    if (observer && sentinel) observer.unobserve(sentinel);
    if (observedSentinel === sentinel) observedSentinel = null;

    Promise.resolve(onLoadMore())
      .catch((err) => {
        if (typeof console !== "undefined" && console.error) {
          console.error("Failed to load older chat history", err);
        }
      })
      .finally(() => {
        loading = false;
        lastScrollTop = container?.scrollTop || 0;
        _schedule(_observeSentinel);
      });
    return true;
  }

  function _requestIntentLoad() {
    if (!observedSentinel || !_isSentinelInLoadRange(observedSentinel)) return false;
    armed = true;
    return _loadFromSentinel(observedSentinel);
  }

  function _bindScrollHandler() {
    if (!container || typeof container.addEventListener !== "function") return;
    if (removeScrollHandler) removeScrollHandler();

    lastScrollTop = container.scrollTop || 0;
    const handleScroll = () => {
      const currentScrollTop = container.scrollTop || 0;
      if (currentScrollTop < lastScrollTop) {
        armed = true;
        if (observedSentinel && _isSentinelInLoadRange(observedSentinel)) {
          _loadFromSentinel(observedSentinel);
        }
      }
      lastScrollTop = currentScrollTop;
    };

    container.addEventListener("scroll", handleScroll, { passive: true });
    removeScrollHandler = () => {
      container.removeEventListener("scroll", handleScroll);
      removeScrollHandler = null;
    };
  }

  function _bindIntentHandlers() {
    if (!container || typeof container.addEventListener !== "function") return;
    if (removeIntentHandlers) removeIntentHandlers();

    const resetWheelGesture = () => {
      if (wheelGestureTimer) clearTimeout(wheelGestureTimer);
      wheelGestureTimer = setTimeout(() => {
        wheelGestureConsumed = false;
        wheelGestureTimer = null;
      }, WHEEL_GESTURE_RESET_MS);
    };

    const handleWheel = (event) => {
      if (!event || event.deltaY >= 0) return;
      resetWheelGesture();
      if (wheelGestureConsumed) return;
      wheelGestureConsumed = true;
      _requestIntentLoad();
    };

    const handleTouchStart = (event) => {
      touchStartY = event?.touches?.[0]?.clientY ?? null;
      touchGestureConsumed = false;
    };

    const handleTouchMove = (event) => {
      const currentY = event?.touches?.[0]?.clientY ?? null;
      if (touchStartY == null || currentY == null) return;
      if (currentY - touchStartY < TOUCH_LOAD_THRESHOLD_PX) return;
      if (touchGestureConsumed) return;
      touchGestureConsumed = true;
      _requestIntentLoad();
    };

    const handleTouchEnd = () => {
      touchStartY = null;
      touchGestureConsumed = false;
    };

    container.addEventListener("wheel", handleWheel, { passive: true });
    container.addEventListener("touchstart", handleTouchStart, { passive: true });
    container.addEventListener("touchmove", handleTouchMove, { passive: true });
    container.addEventListener("touchend", handleTouchEnd, { passive: true });
    container.addEventListener("touchcancel", handleTouchEnd, { passive: true });
    removeIntentHandlers = () => {
      container.removeEventListener("wheel", handleWheel);
      container.removeEventListener("touchstart", handleTouchStart);
      container.removeEventListener("touchmove", handleTouchMove);
      container.removeEventListener("touchend", handleTouchEnd);
      container.removeEventListener("touchcancel", handleTouchEnd);
      removeIntentHandlers = null;
    };
  }

  function _createObserver() {
    if (observer) observer.disconnect();
    observedSentinel = null;
    loading = false;
    armed = true;
    lastScrollTop = container?.scrollTop || 0;
    if (!container) return;

    observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.target !== observedSentinel) continue;

          if (!entry.isIntersecting) {
            armed = true;
            continue;
          }

          _loadFromSentinel(entry.target);
        }
      },
      { root: container, rootMargin: `${LOAD_ROOT_MARGIN_TOP}px 0px 0px 0px` },
    );
    _bindScrollHandler();
    _bindIntentHandlers();
  }

  function observe() {
    if (!observer) _createObserver();
    _observeSentinel();
  }

  function _observeSentinel() {
    if (!observer || !container) return;
    const sentinel = container.querySelector(sentinelSelector);
    if (!sentinel) {
      observedSentinel = null;
      return;
    }
    if (observedSentinel === sentinel) return;
    if (observedSentinel) observer.unobserve(observedSentinel);
    observedSentinel = sentinel;
    observer.observe(sentinel);
  }

  function disconnect() {
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    if (removeScrollHandler) removeScrollHandler();
    if (removeIntentHandlers) removeIntentHandlers();
    if (wheelGestureTimer) clearTimeout(wheelGestureTimer);
    observedSentinel = null;
    loading = false;
    armed = true;
    lastScrollTop = 0;
    wheelGestureConsumed = false;
    wheelGestureTimer = null;
    touchStartY = null;
    touchGestureConsumed = false;
  }

  function refresh() {
    _observeSentinel();
  }

  return { observe, disconnect, refresh };
}
