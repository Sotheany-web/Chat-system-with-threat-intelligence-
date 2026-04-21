
(function (global) {
  /**
   * Accordion
   * @param {Object} options – configuration object
   *        - selector   : CSS selector, single Element, or NodeList/Array of Elements (required)
   *        - oneAtATime : boolean  (default false)
   *        - duration   : number ms (default 250)
   *        - showIcons  : boolean  (default true)
   *        - iconHTML   : string   (default ▾ chevron SVG)
   */
  function Accordion(options = {}) {
    if (!(this instanceof Accordion)) return new Accordion(options);

    const defaults = {
      selector: null,
      oneAtATime: false,
      duration: 250,
      showIcons: true,
      iconHTML:
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6,9 12,15 18,9"/></svg>',
    };

    this.opts = { ...defaults, ...options };

    // Resolve target elements
    const tgt = this.opts.selector;
    this.items =
      typeof tgt === 'string'
        ? document.querySelectorAll(tgt)
        : tgt instanceof Element
        ? [tgt]
        : tgt || []; // NodeList / Array fallback

    this._init();
  }

  /** Initialise each accordion root */
  Accordion.prototype._init = function () {
    this.items.forEach((acc) => {
      const headers = acc.querySelectorAll('.accordion__header');
      const panels  = acc.querySelectorAll('.accordion__panel');

      // Inject icons once
      if (this.opts.showIcons) {
        headers.forEach((h) => {
          if (!h.querySelector('.accordion__icon')) {
            const span = document.createElement('span');
            span.className = 'accordion__icon';
            span.innerHTML = this.opts.iconHTML;
            h.appendChild(span);
          }
        });
      }

      // Collapse all panels initially
      panels.forEach((p) => (p.style.height = 0));
      headers.forEach((h) => h.setAttribute('aria-expanded', 'false'));

      // Click handlers
      headers.forEach((hdr, i) =>
        hdr.addEventListener('click', () => this._toggle(i, headers, panels))
      );
    });
  };

  /** Toggle one panel, obeying one‑at‑a‑time mode if set */
  Accordion.prototype._toggle = function (idx, headers, panels) {
    const { oneAtATime: one, duration: dur } = this.opts;

    headers.forEach((h, i) => {
      const panel      = panels[i];
      const isOpen     = h.getAttribute('aria-expanded') === 'true';
      const shouldOpen = i === idx ? !isOpen : false;

      if (one && i !== idx && isOpen) close(panel, h, dur);
      if (i === idx)   (shouldOpen ? open : close)(panel, h, dur);
    });
  };

  /* Helpers -------------------------------------------------------------- */

  function open(panel, hdr, ms) {
    panel.style.height = panel.scrollHeight + 'px';
    panel.style.transitionDuration = ms + 'ms';
    hdr.setAttribute('aria-expanded', 'true');
    panel.addEventListener(
      'transitionend',
      function handler() {
        if (hdr.getAttribute('aria-expanded') === 'true') panel.style.height = 'auto';
        panel.removeEventListener('transitionend', handler);
      },
      { once: true }
    );
  }

  function close(panel, hdr, ms) {
    panel.style.height = panel.scrollHeight + 'px'; // reset so we can animate from current height
    void panel.offsetHeight;                        // force reflow
    panel.style.transitionDuration = ms + 'ms';
    panel.style.height = 0;
    hdr.setAttribute('aria-expanded', 'false');
  }

  /* Expose globally ------------------------------------------------------ */
  global.Accordion = Accordion;
})(window);
