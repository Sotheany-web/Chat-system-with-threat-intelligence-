/* ─────────────────────────────────────────────
   TemplateRise Image Lightbox  ‑  v2.2
──────────────────────────────────────────────*/
class ImageLightbox {
  constructor(options = {}) {
    this.options = {
      selector: 'img:not(.no-lightbox):not(.logo):not([class*="icon"])',
      excludeClasses: ['no-lightbox', 'logo', 'icon', 'avatar', 'emoji'],
      showCounter: true,
      showZoom: true,
      showDownload: true,
      showFullscreen: true,
      enableKeyboard: true,
      enableTouch: true,
      animationDuration: 300,
      zoomStep: 0.2,
      maxZoom: 3,
      minZoom: 0.5,
      slideshowDelay: 3000,
      minWidth: 0,
      minHeight: 0,
      ...options,
    };

    /* runtime state */
    this.images = [];
    this.currentIndex = 0;
    this.isOpen = false;
    this.currentZoom = 1;
    this.rotation = 0;
    this.translateX = this.translateY = 0;
    this.isDragging = false;
    this.isPlaying = false;
    this.slideshowInterval = null;

    this.init();
  }

  /* ---------- INITIALISATION ---------- */
  init() {
    this.createLightboxHTML();
    this.bindEvents();
    this.initializeImages();

    window.addEventListener('load', () => this.initializeImages());
  }

  /* ---------- DOM TEMPLATE ---------- */
  createLightboxHTML() {
    /* reuse existing DOM if it already exists (SPA safety) */
    if (document.getElementById('imageLightbox')) {
      this.lightbox          = document.getElementById('imageLightbox');
      this.lightboxImage     = this.lightbox.querySelector('#lightboxImage');
      this.lightboxContainer = this.lightbox.querySelector('.lightbox-image-container');
      this.thumbTrack        = this.lightbox.querySelector('.thumb-track');
      return; // nothing else to build
    }

    const html = `
      <div class="image-lightbox" id="imageLightbox" style="display:none">
        <div class="lightbox-overlay"></div>

        <div class="lightbox-container">
          <!-- Header -->
          <div class="lightbox-header">
            <div class="lightbox-counter">
              <span class="current-image">1</span> / <span class="total-images">1</span>
            </div>
            <div class="lightbox-title"></div>
            <div class="lightbox-controls">
              <button class="lightbox-btn" id="playPauseBtn"  title="Play / Pause"><i class="fa fa-play"></i></button>
              <button class="lightbox-btn" id="downloadBtn"   title="Download"><i class="fa fa-download"></i></button>
              <button class="lightbox-btn" id="fullscreenBtn" title="Fullscreen"><i class="fa fa-expand"></i></button>
              <button class="lightbox-btn" id="closeBtn"      title="Close"><i class="fa fa-times"></i></button>
            </div>
          </div>

          <!-- Main viewport -->
          <div class="lightbox-content">
            <button class="lightbox-nav lightbox-prev" id="prevBtn"><i class="fa fa-angle-left"></i></button>

            <div class="lightbox-image-container">
              <img class="lightbox-image" id="lightboxImage" alt="">
              <div class="lightbox-loading"><div class="loading-spinner"></div></div>
            </div>

            <button class="lightbox-nav lightbox-next" id="nextBtn"><i class="fa fa-angle-right"></i></button>
          </div>

          <!-- Footer -->
          <div class="lightbox-footer">
            <div class="lightbox-caption"></div>
            <div class="lightbox-zoom-controls">
              <button class="lightbox-btn" id="rotateLeftBtn"  title="Rotate Left"><i class="fa fa-rotate-left"></i></button>
              <button class="lightbox-btn" id="rotateRightBtn" title="Rotate Right"><i class="fa fa-rotate-right"></i></button>
              <span class="sep"></span>
              <button class="lightbox-btn" id="zoomOutBtn"    title="Zoom Out"><i class="fa fa-search-minus"></i></button>
              <span class="zoom-level">100%</span>
              <button class="lightbox-btn" id="zoomInBtn"     title="Zoom In"><i class="fa fa-search-plus"></i></button>
              <button class="lightbox-btn" id="resetZoomBtn"  title="Reset Zoom"><i class="fa fa-expand-arrows-alt"></i></button>
            </div>
          </div>

          <!-- Thumbnail bar -->
          <div class="lightbox-thumbbar">
            <div class="thumb-track"></div>
          </div>
        </div>
      </div>`;
    document.body.insertAdjacentHTML('beforeend', html);

    /* cache elements */
    this.lightbox          = document.getElementById('imageLightbox');
    this.lightboxImage     = document.getElementById('lightboxImage');
    this.lightboxContainer = this.lightbox.querySelector('.lightbox-image-container');
    this.thumbTrack        = this.lightbox.querySelector('.thumb-track');
  }

  /* ---------- EVENT BINDING ---------- */
  bindEvents() {
    /* close / overlay */
    this.lightbox.querySelector('#closeBtn')
      .addEventListener('click', () => this.close());
    this.lightbox.querySelector('.lightbox-overlay')
      .addEventListener('click', () => this.close());

    /* navigation */
    this.lightbox.querySelector('#prevBtn')
      .addEventListener('click', () => this.prev());
    this.lightbox.querySelector('#nextBtn')
      .addEventListener('click', () => this.next());

    /* slideshow */
    this.lightbox.querySelector('#playPauseBtn')
      .addEventListener('click', () => this.toggleSlideshow());

    /* rotate */
    this.lightbox.querySelector('#rotateLeftBtn')
      .addEventListener('click', () => this.rotateLeft());
    this.lightbox.querySelector('#rotateRightBtn')
      .addEventListener('click', () => this.rotateRight());

    /* zoom controls */
    this.lightbox.querySelector('#zoomInBtn')
      .addEventListener('click', () => this.zoomIn());
    this.lightbox.querySelector('#zoomOutBtn')
      .addEventListener('click', () => this.zoomOut());
    this.lightbox.querySelector('#resetZoomBtn')
      .addEventListener('click', () => this.resetZoom());

    /* download / fullscreen */
    this.lightbox.querySelector('#downloadBtn')
      .addEventListener('click', () => this.download());
    this.lightbox.querySelector('#fullscreenBtn')
      .addEventListener('click', () => this.toggleFullscreen());

    /* keyboard */
    if (this.options.enableKeyboard) {
      document.addEventListener('keydown', (e) => this.handleKeyboard(e));
    }

    /* wheel zoom */
    this.lightboxContainer.addEventListener('wheel', (e) => this.handleWheel(e));

    /* touch & drag */
    if (this.options.enableTouch) {
      this.bindTouchEvents();
    }

    /* loader */
    this.lightboxImage.addEventListener('load',  () => this.hideLoading());
    this.lightboxImage.addEventListener('error', () => this.hideLoading());
  }

  /* ---------- IMAGE LIST ---------- */
  initializeImages() {
    const nodes = document.querySelectorAll(this.options.selector);
    this.images = [];

    nodes.forEach((img) => {
      if (this.options.excludeClasses.some(c => img.classList.contains(c))) return;
      const index = this.images.length;
      this.images.push({
        src     : img.src,
        alt     : img.alt || '',
        title   : img.title || img.alt || '',
        caption : img.dataset.caption || img.alt || '',
      });

      if (!img.dataset.lightboxRegistered) {
        img.dataset.lightboxRegistered = '1';
        // img.style.cursor = 'zoom-in';
        img.addEventListener('click', (e) => {
          e.preventDefault();
          this.open(index);
        });
      }
    });

    this.renderThumbnails();
  }

  /* ---------- THUMBNAILS ---------- */
  renderThumbnails() {
    this.thumbTrack.innerHTML = '';
    this.images.forEach((img, i) => {
      const d = document.createElement('div');
      d.className = 'thumb';
      d.dataset.index = i;
      d.innerHTML = `<img loading="lazy" src="${img.src}" alt="">`;
      d.addEventListener('click', () => this.open(i));
      this.thumbTrack.appendChild(d);
    });
    this.updateActiveThumb();
  }

/* ---------- THUMBNAIL HIGHLIGHT + AUTO‑SCROLL ---------- */
updateActiveThumb() {
  const track   = this.thumbTrack;              // <div class="thumb-track">
  const thumbs  = track.querySelectorAll('.thumb');
  const active  = track.querySelector(`.thumb[data-index="${this.currentIndex}"]`);
  if (!active) return;

  /* highlight */
  thumbs.forEach(t => t.classList.toggle('active', t === active));

  const scrollContainer = track.parentElement; 

  const cRect = scrollContainer.getBoundingClientRect();
  const aRect = active.getBoundingClientRect();

  const overscrollLeft  = aRect.left  - cRect.left;
  const overscrollRight = aRect.right - cRect.right;

  if (overscrollLeft < 0) {
    /* hidden on the left */
    scrollContainer.scrollBy({ left: overscrollLeft - 8, behavior: 'smooth' });
  } else if (overscrollRight > 0) {
    /* hidden on the right */
    scrollContainer.scrollBy({ left: overscrollRight + 8, behavior: 'smooth' });
  }
}



  /* ---------- OPEN / CLOSE ---------- */
  open(index = 0) {
    if (!this.images.length) return;
    this.currentIndex = index;
    this.isOpen = true;
    this.currentZoom = 1;
    this.rotation = 0;
    this.translateX = this.translateY = 0;

    this.lightbox.style.display = 'block';
    requestAnimationFrame(() => this.lightbox.classList.add('visible'));
    document.body.style.overflow = 'hidden';

    this.stopSlideshow();   // stop any existing slideshow
    this.loadImage();
    this.updateUI();
  }
  close() {
    if (!this.isOpen) return;
    this.stopSlideshow();
    this.lightbox.classList.remove('visible');
    setTimeout(() => {
      this.lightbox.style.display = 'none';
      document.body.style.overflow = '';
      this.isOpen = false;
    }, this.options.animationDuration);
  }

  /* ---------- NAVIGATION ---------- */
  next() {
    if (this.images.length <= 1) return;
    this.currentIndex = (this.currentIndex + 1) % this.images.length;
    this.afterSlideChange();
  }
  prev() {
    if (this.images.length <= 1) return;
    this.currentIndex = this.currentIndex ? this.currentIndex - 1 : this.images.length - 1;
    this.afterSlideChange();
  }
  afterSlideChange() {
    this.rotation = 0;
    this.loadImage();
    this.updateUI();
    this.resetZoom(false); // reset zoom but keep rotation zero
  }

  /* ---------- LOAD & UI ---------- */
  loadImage() {
    const imgObj = this.images[this.currentIndex];
    this.showLoading();

    const tmp = new Image();
    tmp.onload = () => {
      this.lightboxImage.src  = imgObj.src;
      this.lightboxImage.alt  = imgObj.alt;
      this.updateImageTransform();
    };
    tmp.src = imgObj.src;
  }
  updateUI() {
    const imgObj = this.images[this.currentIndex];
    this.lightbox.querySelector('.current-image').textContent = this.currentIndex + 1;
    this.lightbox.querySelector('.total-images').textContent   = this.images.length;
    this.lightbox.querySelector('.lightbox-title').textContent = imgObj.title;
    this.lightbox.querySelector('.lightbox-caption').textContent = imgObj.caption;
    this.updateZoomLevel();
    this.updatePlayPauseIcon();
    this.updateActiveThumb();
  }

  /* ---------- SLIDESHOW ---------- */
  startSlideshow() {
    if (this.isPlaying || this.images.length <= 1) return;
    this.isPlaying = true;
    this.slideshowInterval = setInterval(() => this.next(), this.options.slideshowDelay);
    this.updatePlayPauseIcon();
  }
  stopSlideshow() {
    this.isPlaying = false;
    if (this.slideshowInterval) clearInterval(this.slideshowInterval);
    this.slideshowInterval = null;
    this.updatePlayPauseIcon();
  }
  toggleSlideshow() {
    this.isPlaying ? this.stopSlideshow() : this.startSlideshow();
  }
  updatePlayPauseIcon() {
    const icon = this.lightbox.querySelector('#playPauseBtn i');
    if (icon) icon.className = this.isPlaying ? 'fa fa-pause' : 'fa fa-play';
  }

  /* ---------- ROTATE ---------- */
  rotateLeft()  { this.rotation = (this.rotation - 90) % 360; this.updateImageTransform(); }
  rotateRight() { this.rotation = (this.rotation + 90) % 360; this.updateImageTransform(); }

  /* ---------- ZOOM ---------- */
  zoomIn() {
    this.currentZoom = Math.min(this.options.maxZoom, this.currentZoom + this.options.zoomStep);
    this.updateImageTransform(); this.updateZoomLevel();
  }
  zoomOut() {
    this.currentZoom = Math.max(this.options.minZoom, this.currentZoom - this.options.zoomStep);
    this.updateImageTransform(); this.updateZoomLevel();
    if (this.currentZoom <= 1) this.translateX = this.translateY = 0;
  }
  resetZoom(updateTransform = true) {
    this.currentZoom = 1;
    this.translateX = this.translateY = 0;
    if (updateTransform) this.updateImageTransform();
    this.updateZoomLevel();
  }
  updateZoomLevel() {
    this.lightbox.querySelector('.zoom-level').textContent = `${Math.round(this.currentZoom * 100)}%`;
    this.lightboxContainer.style.cursor = this.currentZoom > 1 ? 'grab' : 'default';
  }
  updateImageTransform() {
    this.lightboxImage.style.transform =
      `translate(${this.translateX / this.currentZoom}px, ${this.translateY / this.currentZoom}px) ` +
      `scale(${this.currentZoom}) rotate(${this.rotation}deg)`;
  }

  /* ---------- DOWNLOAD / FULLSCREEN ---------- */
  download() {
    const img = this.images[this.currentIndex];
    const link = document.createElement('a');
    link.href = img.src;
    link.download = (img.title || 'image').replace(/\.[^/.]+$/, '') + '.png';
    document.body.appendChild(link); link.click(); link.remove();
  }
  toggleFullscreen() {
    !document.fullscreenElement ? this.lightbox.requestFullscreen() : document.exitFullscreen();
  }

  /* ---------- KEYBOARD & MOUSE ---------- */
  handleKeyboard(e) {
    if (!this.isOpen) return;
    switch (e.key) {
      case 'Escape': this.close(); break;
      case 'ArrowLeft': this.prev(); break;
      case 'ArrowRight': this.next(); break;
      case ' ': e.preventDefault(); this.toggleSlideshow(); break;
      case 'r': case 'R': this.rotateRight(); break;
      case '+': case '=': e.preventDefault(); this.zoomIn(); break;
      case '-': e.preventDefault(); this.zoomOut(); break;
      case '0': e.preventDefault(); this.resetZoom(); break;
      case 'f': case 'F': this.toggleFullscreen(); break;
      case 'd': case 'D': this.download(); break;
    }
  }
  handleWheel(e) {
    if (!this.isOpen) return;
    e.preventDefault(); e.deltaY < 0 ? this.zoomIn() : this.zoomOut();
  }

  /* ---------- TOUCH & DRAG ---------- */
  bindTouchEvents() {
    let startX, startY, startZoom, startDist, pinch = false;

    /* drag with mouse */
    this.lightboxContainer.addEventListener('mousedown', (e) => {
      if (this.currentZoom <= 1) return;
      this.isDragging = true;
      startX = e.clientX - this.translateX;
      startY = e.clientY - this.translateY;
      this.lightboxContainer.style.cursor = 'grabbing';
    });
    document.addEventListener('mousemove', (e) => {
      if (!this.isDragging) return;
      this.translateX = e.clientX - startX;
      this.translateY = e.clientY - startY;
      this.updateImageTransform();
    });
    document.addEventListener('mouseup', () => {
      this.isDragging = false;
      this.lightboxContainer.style.cursor = this.currentZoom > 1 ? 'grab' : 'default';
    });

    /* touch */
    this.lightboxContainer.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1 && this.currentZoom > 1) {
        this.isDragging = true;
        startX = e.touches[0].clientX - this.translateX;
        startY = e.touches[0].clientY - this.translateY;
      } else if (e.touches.length === 2) {
        pinch = true;
        startZoom = this.currentZoom;
        const [t1, t2] = e.touches;
        startDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
      }
    }, {passive:false});
    this.lightboxContainer.addEventListener('touchmove', (e) => {
      e.preventDefault();
      if (pinch && e.touches.length === 2) {
        const [t1, t2] = e.touches;
        const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
        const scale = dist / startDist;
        this.currentZoom = Math.max(this.options.minZoom, Math.min(this.options.maxZoom, startZoom * scale));
        this.updateZoomLevel();
        this.updateImageTransform();
      } else if (this.isDragging && e.touches.length === 1) {
        this.translateX = e.touches[0].clientX - startX;
        this.translateY = e.touches[0].clientY - startY;
        this.updateImageTransform();
      }
    }, {passive:false});
    this.lightboxContainer.addEventListener('touchend', () => {
      this.isDragging = false; pinch = false;
    });
  }

  /* ---------- LOADING INDICATOR ---------- */
  showLoading() { this.lightbox.querySelector('.lightbox-loading').style.display = 'flex'; }
  hideLoading() { this.lightbox.querySelector('.lightbox-loading').style.display = 'none'; }

  /* ---------- PUBLIC HELPERS ---------- */
  refresh() { this.initializeImages(); }   // can call manually after dynamic inserts
}

