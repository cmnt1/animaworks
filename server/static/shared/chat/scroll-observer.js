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
  const LOAD_ROOT_MARGIN_TOP = 200;

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
    if (!armed || loading) return;

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
    observedSentinel = null;
    loading = false;
    armed = true;
    lastScrollTop = 0;
  }

  function refresh() {
    _observeSentinel();
  }

  return { observe, disconnect, refresh };
}
