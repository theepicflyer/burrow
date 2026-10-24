/* @ds-bundle: {"format":4,"namespace":"Burrow","components":[{"name":"Mascot"},{"name":"Habitat"},{"name":"Trace"},{"name":"Peek"},{"name":"Trail"},{"name":"TrailGap"},{"name":"TrailSteps"},{"name":"Tunnel"},{"name":"Breadcrumbs"},{"name":"Divider"},{"name":"Ring"},{"name":"Meter"},{"name":"Stash"},{"name":"Card"},{"name":"ListRow"},{"name":"BottomNav"},{"name":"Button"},{"name":"Chip"},{"name":"Field"},{"name":"Loader"},{"name":"EmptyState"},{"name":"Toast"},{"name":"Backdrop"},{"name":"Icon"},{"name":"World"}]} */
(function () {
  var React = window.React, h = React.createElement;
  /* ---------- the cast: one SVG string generator per animal, also used to export the asset SVGs ---------- */
  var INK = '#2b2240', CHEEK = '#ff8fb3', DROP = '#5db6ff', HALO = '#fffaf0', W = 2.8;
  var C = {
    hamster: '#eea955', hamsterDark: '#cf8a38', hamsterLight: '#fff1dc', muzzle: '#fffaf2', pink: '#f6a3b4', nose: '#ef8aa2',
    squirrel: '#c8693a', squirrelDark: '#9a4722', squirrelLight: '#f8e3c9', tailLight: '#eb9c64',
    molerat: '#f3b2a6', moleratDark: '#d4837a', moleratLight: '#fbd6cd', tooth: '#fbf3df',
    beaver: '#8b5a3c', beaverDark: '#664028', beaverBelly: '#a2704c', muzzleB: '#dcbb95', beaverTail: '#4f3a32', beaverScale: '#6d5448', orange: '#f29a3a', hands: '#4a3226',
    soil: '#9a6a45', soilDeep: '#4a3024', acorn: '#d99a4e', acornCap: '#7a4e2d', seed: '#3b3240', twig: '#8a5a3b', leaf: '#34c08f', chip: '#e7c49a'
  };
  function st(w) { return ' stroke="' + INK + '" stroke-width="' + (w || W) + '" stroke-linecap="round" stroke-linejoin="round"'; }
  function line(d, w, color, op) { return '<path d="' + d + '" fill="none" stroke="' + (color || INK) + '" stroke-width="' + (w || 2.2) + '" stroke-linecap="round" stroke-linejoin="round"' + (op ? ' opacity="' + op + '"' : '') + '/>'; }
  function el(cx, cy, rx, ry, fill, w, op) { return '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + rx + '" ry="' + ry + '" fill="' + fill + '"' + (w ? st(w) : '') + (op ? ' opacity="' + op + '"' : '') + '/>'; }
  function path(d, fill, w, op) { return '<path d="' + d + '" fill="' + fill + '"' + (w ? st(w) : '') + (op ? ' opacity="' + op + '"' : '') + '/>'; }
  function ep(cx, cy, rx, ry) { return 'M' + (cx - rx) + ' ' + cy + ' A' + rx + ' ' + ry + ' 0 1 0 ' + (cx + rx) + ' ' + cy + ' A' + rx + ' ' + ry + ' 0 1 0 ' + (cx - rx) + ' ' + cy + ' Z'; }
  /* silhouette parts get one thick outer outline (drawn first, doubled) and then their fills: clean sticker edges, no inner seams */
  function figure(parts) {
    var o = '', f = '';
    parts.forEach(function (p) { var t = p[2] ? ' transform="' + p[2] + '"' : ''; o += '<path d="' + p[0] + '"' + t + '/>'; f += '<path d="' + p[0] + '" fill="' + p[1] + '"' + t + '/>'; });
    return '<g fill="' + HALO + '" stroke="' + HALO + '" stroke-width="' + (W * 2 + 5) + '" stroke-linejoin="round">' + o + '</g>' +
      '<g fill="' + INK + '" stroke="' + INK + '" stroke-width="' + (W * 2) + '" stroke-linejoin="round">' + o + '</g>' + f;
  }
  function shadow(cx, rx) { return el(cx, 112, rx, 4.5, INK, 0, '.14'); }

  /* faces. f = {x, y: eye line, dx: half eye gap, r: eye radius, m: [x, y] mouth anchor, style: 'y' (nose-to-mouth Y) | 'lip', z: [x, y], drop: [x, y]} */
  function eyes(m, f) {
    var a = f.x - f.dx, b = f.x + f.dx, y = f.y, r = f.r, k = r * 1.2, w = Math.max(1.8, r * .45);
    if (m === 'joy') return line('M' + (a - k) + ' ' + (y + r * .3) + ' Q' + a + ' ' + (y - r * 1.2) + ' ' + (a + k) + ' ' + (y + r * .3) + ' M' + (b - k) + ' ' + (y + r * .3) + ' Q' + b + ' ' + (y - r * 1.2) + ' ' + (b + k) + ' ' + (y + r * .3), w);
    if (m === 'sleepy') return line('M' + (a - k) + ' ' + y + ' Q' + a + ' ' + (y + r) + ' ' + (a + k) + ' ' + y + ' M' + (b - k) + ' ' + y + ' Q' + b + ' ' + (y + r) + ' ' + (b + k) + ' ' + y, w);
    var rr = m === 'wow' ? r * 1.25 : r, out = '';
    [a, b].forEach(function (x) {
      if (m === 'busy') out += path('M' + (x - rr) + ' ' + (y - rr * .15) + ' A' + rr + ' ' + rr + ' 0 0 0 ' + (x + rr) + ' ' + (y - rr * .15) + ' Z', INK);
      else out += '<circle cx="' + x + '" cy="' + y + '" r="' + rr + '" fill="' + INK + '"/>';
      out += '<circle cx="' + (x + rr * .38) + '" cy="' + (y - rr * (m === 'busy' ? -.2 : .38)) + '" r="' + Math.max(.9, rr * .32) + '" fill="#fff"/>' +
        '<circle cx="' + (x - rr * .35) + '" cy="' + (y + rr * .4) + '" r="' + Math.max(.5, rr * .14) + '" fill="#fff" opacity=".8"/>';
    });
    if (m === 'worried') out += line('M' + (a - k) + ' ' + (y - r - 2.5) + ' L' + (a + k * .8) + ' ' + (y - r - 5.5) + ' M' + (b + k) + ' ' + (y - r - 2.5) + ' L' + (b - k * .8) + ' ' + (y - r - 5.5), 2);
    if (m === 'busy') out += line('M' + (a - k) + ' ' + (y - r - 1) + ' L' + (a + k) + ' ' + (y - r + 1.5) + ' M' + (b + k) + ' ' + (y - r - 1) + ' L' + (b - k) + ' ' + (y - r + 1.5), 2);
    return out;
  }
  function mouth(m, f) {
    var x = f.m[0], y = f.m[1], s = f.ms || 1, yv = f.style === 'y';
    var stem = yv ? line('M' + x + ' ' + (y - 3 * s) + ' V' + y, 1.8) : '';
    if (m === 'joy') return stem + path('M' + (x - 6 * s) + ' ' + y + ' Q' + x + ' ' + (y + 10 * s) + ' ' + (x + 6 * s) + ' ' + y + ' Z', INK, 1.8) + path('M' + (x - 3 * s) + ' ' + (y + 4.5 * s) + ' Q' + x + ' ' + (y + 7 * s) + ' ' + (x + 3 * s) + ' ' + (y + 4.5 * s) + ' Z', CHEEK);
    if (m === 'sleepy') return stem + '<circle cx="' + x + '" cy="' + (y + 2 * s) + '" r="' + (2 * s) + '" fill="none"' + st(1.8) + '/>';
    if (m === 'worried') return stem + line('M' + (x - 5 * s) + ' ' + (y + 3 * s) + ' Q' + (x - 2.5 * s) + ' ' + y + ' ' + x + ' ' + (y + 3 * s) + ' Q' + (x + 2.5 * s) + ' ' + (y + 6 * s) + ' ' + (x + 5 * s) + ' ' + (y + 3 * s), 1.8);
    if (m === 'wow') return stem + el(x, y + 3 * s, 2.6 * s, 3.4 * s, INK);
    if (m === 'busy') return stem + line('M' + (x - 4 * s) + ' ' + (y + 1 * s) + ' l2 ' + (2 * s) + ' l2 ' + (-2 * s) + ' l2 ' + (2 * s) + ' l2 ' + (-2 * s), 1.8);
    if (yv) return stem + line('M' + x + ' ' + y + ' Q' + (x - 2.5 * s) + ' ' + (y + 2.8 * s) + ' ' + (x - 5 * s) + ' ' + (y + 1.4 * s) + ' M' + x + ' ' + y + ' Q' + (x + 2.5 * s) + ' ' + (y + 2.8 * s) + ' ' + (x + 5 * s) + ' ' + (y + 1.4 * s), 1.8);
    return line('M' + (x - 5 * s) + ' ' + y + ' Q' + x + ' ' + (y + 3.5 * s) + ' ' + (x + 5 * s) + ' ' + y, 1.8);
  }
  function extras(m, f) {
    if (m === 'sleepy') { var zd = 'M' + f.z[0] + ' ' + f.z[1] + ' h7 l-7 8 h7 M' + (f.z[0] + 10) + ' ' + (f.z[1] - 11) + ' h5 l-5 6 h5'; return line(zd, 6, HALO) + line(zd, 2.4); }
    if (m === 'worried') { var d = f.drop; var dd = 'M' + d[0] + ' ' + d[1] + ' C' + (d[0] - 4) + ' ' + (d[1] + 7) + ' ' + (d[0] - 5) + ' ' + (d[1] + 11) + ' ' + d[0] + ' ' + (d[1] + 11) + ' C' + (d[0] + 5) + ' ' + (d[1] + 11) + ' ' + (d[0] + 4) + ' ' + (d[1] + 7) + ' ' + d[0] + ' ' + d[1] + ' Z'; return '<path d="' + dd + '" fill="' + HALO + '" stroke="' + HALO + '" stroke-width="5" stroke-linejoin="round"/>' + path(dd, DROP, 2); }
    if (m === 'busy') return f.busy || '';
    return '';
  }
  function face(m, f) { return eyes(m, f) + mouth(m, f) + extras(m, f); }
  function blush(x1, x2, y, rx) { return el(x1, y, rx || 5, 3, CHEEK, 0, '.5') + el(x2, y, rx || 5, 3, CHEEK, 0, '.5'); }
  function mirror(d) { return d.replace(/(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/g, function (s, x, y) { return (120 - x) + ' ' + y; }); }

  /* accessories, reused by the Trace component */
  function seedAt(x, y, s, rot) { s = s || 1; return '<g transform="translate(' + x + ' ' + y + ') rotate(' + (rot || 0) + ') scale(' + s + ')">' + path('M0 -9 C6 -5 6 5 0 9 C-6 5 -6 -5 0 -9 Z', C.seed, 2.2) + line('M0 -6 V6', 1.6, '#fff4e2') + line('M-2.6 -3 V3 M2.6 -3 V3', 1.1, '#bdb2cf') + '</g>'; }
  function acornAt(x, y, s, rot) { s = s || 1; return '<g transform="translate(' + x + ' ' + y + ') rotate(' + (rot || 0) + ') scale(' + s + ')">' + path('M-7 -1 C-7 7 -3 11 0 12 C3 11 7 7 7 -1 Z', C.acorn, 2.2) + path('M-4 1 C-4 6 -2 8 -1 9', 'none') + line('M-4 2 C-4 6 -2.5 8 -1 9', 1.4, '#fff', '.5') + path('M-9 -1 C-9 -7 -4 -9 0 -9 C4 -9 9 -7 9 -1 Z', C.acornCap, 2.2) + line('M0 -9 L1 -13', 2.2) + line('M-5 -5 L-2 -2 M0 -6 L3 -3 M4 -6 L6 -4', 1.1, '#b07a52') + '</g>'; }
  function twigAt(x1, y1, x2, y2, w) { w = w || 5; return line('M' + x1 + ' ' + y1 + ' L' + x2 + ' ' + y2, w + 4.4) + line('M' + x1 + ' ' + y1 + ' L' + x2 + ' ' + y2, w, C.twig) + line('M' + x1 + ' ' + (y1 - 1) + ' L' + x2 + ' ' + (y2 - 1), 1, '#b98a62'); }

  var CAST = {
    /* Bao: Syrian hamster, makan's host. Golden back, cream bib, pink hands holding a sunflower seed. */
    hamster: function (m) {
      var body = 'M60 20 C74 20 86 26 91 38 C94 44 95 50 95 54 L99 57 L96 59.5 L101 64 L97 66 L101 71 L96.5 72.5 C102 82 104 92 98 100 C92 108 78 111 60 111 C42 111 28 108 22 100 C16 92 18 82 23.5 72.5 L19 71 L23 66 L19 64 L24 59.5 L21 57 L25 54 C25 50 26 44 29 38 C34 26 46 20 60 20 Z';
      var ear = 'M31 37 C23 25 28 12 39 12 C47 13 50 22 47 33 Z', foot = 'M33 110 C33 104 39 102.5 45 103.5 C51 104.5 54 108.5 52 112 C46 114.5 35 114 33 110 Z';
      var arm = 'M44.5 92 C45 86 49 81.5 53 79.5 L56.5 82.5 C53.5 85 51 89 50 93 Z';
      return shadow(60, 38) + figure([[ear, C.hamster], [mirror(ear), C.hamster], [body, C.hamster], [foot, C.pink], [mirror(foot), C.pink]]) +
        path('M34.5 33 C29 24 32.5 16 39 16 C43.5 17 45.5 22.5 44 30 Z', C.pink, 0, '.95') + path(mirror('M34.5 33 C29 24 32.5 16 39 16 C43.5 17 45.5 22.5 44 30 Z'), C.pink, 0, '.95') +
        path('M37 33 C45 22.5 75 22.5 83 33 C77 37.5 68 39 60 39 C52 39 43 37.5 37 33 Z', C.hamsterDark, 0, '.35') +
        path('M33 70 C36 62 43 58 47.5 58 L50.5 61.5 L53.5 57.5 L57 60.5 L60 56.5 L63 60.5 L66.5 57.5 L69.5 61.5 L72.5 58 C77 58 84 62 87 70 C92 80 92 94 87 102 C82 108 72 110.5 60 110.5 C48 110.5 38 108 33 102 C28 94 28 80 33 70 Z', C.hamsterLight) +
        line('M27 80 C26 90 28 98 33 104 M93 80 C94 90 92 98 87 104', 2, C.hamsterDark, '.5') +
        el(60, 64.5, 11.5, 8.5, C.muzzle) +
        line('M49 64 L35 61 M49 66.5 L34 67.5 M49 69 L36 73.5 M71 64 L85 61 M71 66.5 L86 67.5 M71 69 L84 73.5', 1, INK, '.5') +
        blush(36.5, 83.5, 64.5) +
        path('M56.4 59.6 C56.4 57.2 63.6 57.2 63.6 59.6 C63.6 61.7 61.2 63.3 60 63.3 C58.8 63.3 56.4 61.7 56.4 59.6 Z', C.nose, 1.6) +
        face(m, { x: 60, y: 48.5, dx: 15, r: 5.4, m: [60, 66.3], style: 'y', ms: .9, z: [92, 22], drop: [96, 38],
          busy: path('M40 58 l3 -2 l1 3 Z M80 56 l3 1 l-2 3 Z M84 64 l2 -2 l2 2 Z', '#e8b25e', 1.4) + line('M34 52 l-4 -2 M88 50 l4 -2', 1.6, INK, '.5') }) +
        line('M51.5 83 C47.5 86.5 45.5 91 45.5 96 M68.5 83 C72.5 86.5 74.5 91 74.5 96', 1.8, C.hamsterDark, '.55') +
        seedAt(60, 78.5, .8, 0) +
        el(54.6, 80, 4, 3.3, C.pink, 1.6) + el(65.4, 80, 4, 3.3, C.pink, 1.6) +
        line('M37 111 v2 M41 111.5 v2 M45 111.5 v2 M83 111 v2 M79 111.5 v2 M75 111.5 v2', 1.1, INK, '.55') +
        line('M46 99 q2 2 4 0 M68 97 q2 2 4 0 M56 104 q2 2 4 0', 1.2, C.hamsterDark, '.6');
    },
    /* Kacang: red squirrel, money's host. Ear tufts, white eye rings, feathery tail, holds an acorn. */
    squirrel: function (m) {
      function flip(d) { return d.replace(/(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/g, function (s, x, y) { return +(104 - x).toFixed(2) + ' ' + y; }); }
      var tail = 'M66 104 C90 108 108 96 109 78 C110 66 104 58 106 46 C108 32 100 16 84 12 C72 9 60 16 61 27 C62 35 71 38 77 33 C81 30 87 33 87 41 C87 53 79 61 81 75 C82 87 76 97 66 100 Z';
      var tufts = ['M106.5 75 C112 73 114.5 66.5 112.5 61.5 C110.5 66 108 67 105.5 66 Z', 'M105 56 C110.5 54 113 47.5 111 42.5 C109 47 106.5 48 104 47 Z', 'M101.5 33 C107 32 110 26 108.5 20.5 C105.5 25.5 103 26.5 100 25.5 Z', 'M87 14.5 C90.5 9 97 7 101.5 9.5 C96.5 10.5 93.5 12.5 92 16 Z', 'M93 102.5 C99.5 104.5 105 101 107 96.5 C103 98.5 99 98.5 96 97.5 Z', 'M66 14 C64 9 66 5 70 3.5 C69.5 7 70.5 10 72.5 11.5 Z'];
      var body = 'M52 60 C66 60 75 72 75 88 C75 102 65 111 52 111 C39 111 30 102 30 89 C30 74 38 60 52 60 Z';
      var head = 'M52 21 C64 21 72 29 72 40 C72 45 71 49 68 52 L72.5 55 L66.5 56.5 C63 60.5 58 63 52 63 C46 63 41 60.5 37.5 56.5 L31.5 55 L36 52 C33 49 32 45 32 40 C32 29 40 21 52 21 Z';
      var ear = 'M37 32 C35.5 23 35.5 16 39 10 C43 14.5 47 20 47 28 Z', tuft = 'M37.6 13 C35.8 10.5 36.2 7.6 38.4 5.6 C39 7.8 40.4 8.6 42.2 8.2 C42 10.6 41 12.4 39.6 13.8 Z';
      var inner = 'M39.8 26 C39 21 39.2 17 40.8 13.8 C42.6 17 43.8 21 43.8 25.5 Z';
      /* hind feet, sitting: round toes forward, mirrored about the body's centre (x 52) */
      var foot = 'M31 108.5 C31 104 36 102 42 102.5 C47.5 103 50.5 106 49.5 109.5 C45 112.5 34 112.5 31 108.5 Z', toes = 'M37.5 111.2 v-2.6 M42 111.4 v-2.6 M46 110.6 v-2.4';
      var parts = [[tail, C.squirrel]].concat(tufts.map(function (t) { return [t, C.squirrel]; }));
      return shadow(64, 42) + figure(parts.concat([[body, C.squirrel], [foot, C.squirrel], [flip(foot), C.squirrel], [tuft, C.squirrelDark], [flip(tuft), C.squirrelDark], [ear, C.squirrel], [flip(ear), C.squirrel], [head, C.squirrel]])) +
        line('M84 20 C96 24 102 36 100 50 M96 62 C100 74 98 86 90 96 M72 18 C78 14 86 15 92 21', 3, C.tailLight, '.75') +
        line('M80 41 C84 52 78 62 80 74', 1.6, C.squirrelDark, '.55') +
        path(inner, C.squirrelDark, 0, '.45') + path(flip(inner), C.squirrelDark, 0, '.45') +
        path('M52 68 C60 68 65 77 65 88 C65 100 59 106 52 106 C45 106 39 100 39 88 C39 77 44 68 52 68 Z', C.squirrelLight) +
        line('M64 84 C72 84 76 94 72.5 104', 1.8, C.squirrelDark, '.6') +
        path(foot, C.squirrel, 1.8) + path(flip(foot), C.squirrel, 1.8) + line(toes + ' ' + flip(toes), 1.3, C.squirrelDark, '.8') +
        path('M42 50 C44.5 46.8 48.5 47.2 52 47.2 C55.5 47.2 59.5 46.8 62 50 C64 55.5 59 60.5 52 60.5 C45 60.5 40 55.5 42 50 Z', C.squirrelLight) +
        el(42.5, 41, 6, 5.9, C.squirrelLight) + el(61.5, 41, 6, 5.9, C.squirrelLight) +
        line('M45 53 L33 50.5 M45 55 L32.5 56.5 M59 53 L71 50.5 M59 55 L71.5 56.5', 1, INK, '.5') +
        blush(38, 66, 51.5, 3.6) +
        path('M49.2 48.6 C49.2 46.9 54.8 46.9 54.8 48.6 C54.8 50.1 53 51.2 52 51.2 C51 51.2 49.2 50.1 49.2 48.6 Z', INK) + el(51, 48, 1.2, .7, '#fff', 0, '.6') +
        face(m, { x: 52, y: 41, dx: 9.5, r: 4.6, m: [52, 53.6], style: 'y', ms: .75, z: [76, 30], drop: [72, 32],
          busy: path('M28 102 l3 -3 l2 3 Z M76 104 l3 -2 l1 3 Z', C.soil, 1.2) + '<circle cx="27" cy="97" r="1.6" fill="' + C.soil + '"/><circle cx="78" cy="98" r="1.4" fill="' + C.soil + '"/>' }) +
        line('M38.5 84 C38.5 78 41 75.5 44 74.5 M65.5 84 C65.5 78 63 75.5 60 74.5', 1.6, C.squirrelDark, '.7') +
        acornAt(52, 77, 1.05, 0) +
        el(44.5, 76, 4.5, 3.6, C.squirrel, 1.6) + el(59.5, 76, 4.5, 3.6, C.squirrel, 1.6);
    },
    /* Gali: naked mole rat. Wrinkled pink skin, tiny eyes, huge incisors, digging claws on the rim of its hole. */
    molerat: function (m) {
      var body = 'M33 106 C32 98 31 92 34 87 C31 84 31 79 34 75 C32 70 33 64 37 59 C39 50 44 41 52 37 C55 35 58 34 60 34 C62 34 65 35 68 37 C76 41 81 50 83 59 C87 64 88 70 86 75 C89 79 89 84 86 87 C89 92 88 98 87 106 Z';
      var mound = 'M6 106 C6 97 18 95 28 99 C40 104 80 104 92 99 C102 95 114 97 114 106 C114 114 6 114 6 106 Z';
      var paw = 'M30 101 C30 96.5 35 95.5 39.5 96 C44.5 96.5 46.5 100 45 103.5 C41 106 32 105.5 30 101 Z';
      return figure([[ep(60, 101, 45, 11.5), C.soilDeep], [body, C.molerat], [mound, C.soil], [ep(16, 95, 5, 5), C.soil], [ep(104.5, 93, 4, 4), C.soil], [ep(97, 112, 3, 3), C.soil], [paw, C.molerat], [mirror(paw), C.molerat]]) +
        line('M48 40 C54 37 62 37 67 39.5', 3, C.moleratLight, '.9') +
        line('M42 49 Q60 43.5 78 49 M45 44.5 Q60 40 75 44.5', 1.7, C.moleratDark, '.65') +
        line('M37.5 61 Q45 63.5 48 59 M82.5 61 Q75 63.5 72 59 M36 80 Q60 88 84 80 M35 92 Q60 100 85 92 M34.5 71 Q40 74 44 72 M85.5 71 Q80 74 76 72', 1.7, C.moleratDark, '.65') +
        el(60, 64, 10.5, 7, C.moleratLight, 0, '.8') +
        blush(44, 76, 64, 4) +
        line('M47 64 L34 60 M47 67 L33 68 M73 64 L86 60 M73 67 L87 68 M52 35.5 l-2 -4 M60 34 v-4.5 M68 35.5 l2 -4 M40 52 l-4 -2 M80 52 l4 -2', 1, INK, '.45') +
        el(60, 62.5, 6, 3.8, C.moleratDark, 1.6) + '<circle cx="57.6" cy="62.5" r=".9" fill="' + INK + '"/><circle cx="62.4" cy="62.5" r=".9" fill="' + INK + '"/>' +
        face(m, { x: 60, y: 53.5, dx: 10, r: 2.5, m: [60, 68.5], style: 'lip', ms: .9, z: [86, 28], drop: [88, 42],
          busy: path('M18 84 l4 -3 l2 4 Z M100 80 l3 -4 l3 4 Z M24 74 l3 -2 l1 3 Z M95 70 l3 -1 l-1 3 Z', C.soil, 1.4) + line('M28 88 l-4 -4 M92 86 l4 -4', 1.4, INK, '.5') }) +
        '<rect x="55.2" y="69.4" width="4.4" height="12.5" rx="1.6" fill="' + C.tooth + '"' + st(1.8) + '/><rect x="60.4" y="69.4" width="4.4" height="12.5" rx="1.6" fill="' + C.tooth + '"' + st(1.8) + '/>' +
        line('M31.5 98.5 l-1.5 -3.5 M35 97 l-.5 -4 M39 96.5 l.5 -4 M88.5 98.5 l1.5 -3.5 M85 97 l.5 -4 M81 96.5 l-.5 -4', 1.6, C.tooth) +
        line('M31.5 98.5 l-1.5 -3.5 M35 97 l-.5 -4 M39 96.5 l.5 -4 M88.5 98.5 l1.5 -3.5 M85 97 l.5 -4 M81 96.5 l-.5 -4', .6, INK, '.6') +
        '<circle cx="24" cy="108" r="1.2" fill="#6e4a30"/><circle cx="50" cy="109" r="1" fill="#6e4a30"/><circle cx="76" cy="108.5" r="1.3" fill="#6e4a30"/><circle cx="100" cy="106" r="1" fill="#6e4a30"/>';
    },
    /* Kayu: beaver. Heavy brown body, puffy whisker pads, orange incisors, scaly paddle tail, webbed feet, carries a branch. */
    beaver: function (m) {
      var body = 'M58 25 C76 25 88 36 90 50 L94 53 L90.5 56 L95 60 L90 61.5 C96 72 98 88 93 99 C87 108 74 111 58 111 C42 111 29 108 23 99 C18 88 20 72 26 61.5 L21 60 L25.5 56 L22 53 L26 50 C28 36 40 25 58 25 Z';
      var foot = 'M30 106 C26 104 19.5 106 18 110.5 C22 114.5 36 114.5 42.5 112 C42.5 108 36 106 30 106 Z';
      return shadow(60, 42) + figure([[ep(98, 102, 20, 9), C.beaverTail, 'rotate(-14 98 102)']]) +
        '<g transform="rotate(-14 98 102)">' + line('M84 98 L114 105 M85 105 L112 97 M92 94 L106 110 M92 110 L106 94', 1.3, C.beaverScale) + '</g>' +
        figure([[ep(35.5, 33, 6.5, 6.5), C.beaver], [ep(80.5, 33, 6.5, 6.5), C.beaver], [body, C.beaver], [foot, C.beaverTail], [mirror(foot).replace(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g, function (s, x, y) { return (+x - 4) + ' ' + y; }), C.beaverTail]]) +
        el(35.5, 33, 3, 3, C.beaverDark) + el(80.5, 33, 3, 3, C.beaverDark) +
        path('M58 66 C72 66 85 76 85 90 C85 102 73 108.5 58 108.5 C43 108.5 31 102 31 90 C31 76 44 66 58 66 Z', C.beaverBelly, 0, '.75') +
        line('M33 72 q3 -2 6 0 M78 74 q3 -2 6 0 M44 34 q3 -2 6 0 M67 33 q3 -2 6 0 M30 88 q3 -2 6 0 M82 90 q3 -2 6 0 M56 30 q2 -1.5 4 0', 1.4, C.beaverDark, '.8') +
        el(51, 61, 9, 7, C.muzzleB, 1.2) + el(65, 61, 9, 7, C.muzzleB, 1.2) +
        '<g fill="' + C.beaverDark + '" opacity=".6"><circle cx="47" cy="60" r=".9"/><circle cx="50" cy="63" r=".9"/><circle cx="46" cy="64" r=".9"/><circle cx="69" cy="60" r=".9"/><circle cx="66" cy="63" r=".9"/><circle cx="70" cy="64" r=".9"/></g>' +
        line('M43 60 L30 57 M43 63 L29 64 M73 60 L86 57 M73 63 L87 64', 1, INK, '.5') +
        blush(37, 79, 54, 4) +
        path('M52 52.5 C52 50 64 50 64 52.5 C64 55.5 61 57.2 58 57.2 C55 57.2 52 55.5 52 52.5 Z', INK) + el(55.5, 52, 1.6, 1, '#fff', 0, '.7') +
        face(m, { x: 58, y: 43, dx: 13, r: 3.9, m: [58, 66], style: 'lip', ms: .8, z: [92, 24], drop: [94, 36],
          busy: path('M86 74 l4 -2 l1 3 l-4 1 Z M92 66 l3 -1 l0 3 Z M24 72 l4 -1 l-1 3 Z', C.chip, 1.2) }) +
        '<rect x="53.6" y="66.4" width="4.4" height="9" rx="1.4" fill="' + C.orange + '"' + st(1.8) + '/><rect x="58.2" y="66.4" width="4.4" height="9" rx="1.4" fill="' + C.orange + '"' + st(1.8) + '/>' +
        twigAt(28, 82, 92, 76, 4.5) + el(60, 79, 3.2, 2.6, C.chip, 1.2) + path('M89 76.5 C87.5 68 93 62.5 99 62.5 C100 70 96 75.5 89 76.5 Z', C.leaf, 1.8) + line('M84 77.5 L81 69.5', 2.6) + line('M84 77.5 L81 69.5', 1.4, C.twig) +
        el(43, 82, 5.5, 4.6, C.hands, 1.6) + el(76, 79, 5.5, 4.6, C.hands, 1.6) + line('M40 80 v3 M43 79.5 v3 M46 80 v3 M73 77 v3 M76 76.5 v3 M79 77 v3', 1, '#8a7268') +
        line('M22 111 v1.6 M27 112 v1.6 M32 112 v1.6 M37 111.5 v1.6 M90 111 v1.6 M85 112 v1.6 M80 112 v1.6 M75 111.5 v1.6', 1.1, '#8a7268');
    }
  };
  var NAMES = { hamster: 'Bao', squirrel: 'Kacang', molerat: 'Gali', beaver: 'Kayu' };
  var ALIAS = { bao: 'hamster', kacang: 'squirrel', gali: 'molerat', kayu: 'beaver' };
  var MOODS = ['happy', 'joy', 'busy', 'sleepy', 'worried', 'wow'];
  function mascotSVG(character, mood, label) {
    var c = ALIAS[character] || (CAST[character] ? character : 'hamster');
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120" role="img" aria-label="' + (label || NAMES[c]) + '">' + CAST[c](mood || 'happy') + '</svg>';
  }
  /* ---------- traces: the natural things each animal leaves around the app (32×32) ---------- */
  function crumb(x, y, s, rot) { return '<g transform="translate(' + x + ' ' + y + ') rotate(' + (rot || 0) + ') scale(' + (s || 1) + ')">' + path('M-3 -2 L2 -3 L3 1.5 L-1 3 Z', '#dba04f', 1.3) + '</g>'; }
  function leafAt(x, y, s, rot, fill) { return '<g transform="translate(' + x + ' ' + y + ') rotate(' + (rot || 0) + ') scale(' + (s || 1) + ')">' + path('M0 -13 C3 -11 2 -8 5 -8 C8 -8 7 -4 5 -3 C9 -3 10 1 6 2 C9 4 7 8 4 7 C4 10 2 11 0 12 C-2 11 -4 10 -4 7 C-7 8 -9 4 -6 2 C-10 1 -9 -3 -5 -3 C-7 -4 -8 -8 -5 -8 C-2 -8 -3 -11 0 -13 Z', fill || C.leaf, 1.8) + line('M0 -8 V15', 1.4) + '</g>'; }
  function printAt(x, y, s, rot, fill, op) { return '<g transform="translate(' + x + ' ' + y + ') rotate(' + (rot || 0) + ') scale(' + (s || 1) + ')"' + (op ? ' opacity="' + op + '"' : '') + ' fill="' + (fill || C.soil) + '"><ellipse cx="0" cy="3" rx="5.2" ry="4.6"/><circle cx="-6" cy="-3.6" r="2.1"/><circle cx="-2.2" cy="-6.6" r="2.1"/><circle cx="2.2" cy="-6.6" r="2.1"/><circle cx="6" cy="-3.6" r="2.1"/></g>'; }
  var TRACES = {
    seed: function () { return seedAt(16, 16, 1.35, 25); },
    crumbs: function () { return crumb(9, 19, 1.5, 10) + crumb(20, 10, 1.2, -30) + crumb(23, 23, 1.3, 40) + crumb(14, 27, .8, 0); },
    sunflower: function () {
      var p = ''; for (var i = 0; i < 12; i++) p += '<ellipse cx="16" cy="6" rx="3" ry="5.6" fill="#ffc83a"' + st(1.6) + ' transform="rotate(' + (i * 30) + ' 16 16)"/>';
      return p + '<circle cx="16" cy="16" r="6.8" fill="#7a4e2d"' + st(1.8) + '/><circle cx="14" cy="14.5" r=".9" fill="#3b2a20"/><circle cx="18" cy="15.5" r=".9" fill="#3b2a20"/><circle cx="15.5" cy="18.5" r=".9" fill="#3b2a20"/><circle cx="17.5" cy="12.5" r=".8" fill="#3b2a20"/>';
    },
    berry: function () { return line('M16 4 C16 8 14 10 12 12 M16 4 C17 8 19 10 21 13', 1.6) + leafAt(19, 6, .45, 60) + '<circle cx="11" cy="19" r="6" fill="#5867d1"' + st(1.8) + '/><circle cx="21" cy="21" r="6.4" fill="#4b59c2"' + st(1.8) + '/><circle cx="9" cy="17" r="1.5" fill="#fff" opacity=".6"/><circle cx="19" cy="19" r="1.6" fill="#fff" opacity=".6"/>' + line('M10 22.5 l1 -1 l1 1 M20 25 l1 -1 l1 1', 1.1); },
    acorn: function () { return acornAt(16, 17, 1.2, -12); },
    leaf: function () { return leafAt(16, 15, 1.05, 0); },
    pinecone: function () { var r = ''; [[16, 9, 4], [12, 14, 4.5], [20, 14, 4.5], [16, 15, 4.5], [12, 20, 4.2], [20, 20, 4.2], [16, 21, 4.2], [16, 26, 3.6]].forEach(function (q) { r += path('M' + (q[0] - q[2]) + ' ' + q[1] + ' Q' + q[0] + ' ' + (q[1] + q[2] * 1.4) + ' ' + (q[0] + q[2]) + ' ' + q[1] + ' Q' + q[0] + ' ' + (q[1] - q[2] * .5) + ' ' + (q[0] - q[2]) + ' ' + q[1] + ' Z', '#9a6438', 1.4); }); return line('M16 3 V7', 2) + r; },
    mushroom: function () { return path('M12 18 C12 24 11 28 13 29 H19 C21 28 20 24 20 18 Z', '#f6e7cf', 1.8) + path('M4 18 C4 9 10 4 16 4 C22 4 28 9 28 18 C22 20 10 20 4 18 Z', '#b5683a', 1.8) + el(11, 11, 2.2, 1.6, '#f3c79a') + el(20, 9, 1.8, 1.3, '#f3c79a') + el(23, 14, 1.4, 1.1, '#f3c79a') + line('M13 24 h6', 1, INK, '.4'); },
    footprint: function () { return printAt(16, 17, 1.25, 0); },
    hole: function () { return el(16, 20, 13, 6.5, C.soil, 2.2) + el(16, 19.5, 9, 4, C.soilDeep) + '<circle cx="4" cy="15" r="2.5" fill="' + C.soil + '"' + st(1.8) + '/><circle cx="28" cy="16" r="2" fill="' + C.soil + '"' + st(1.8) + '/>'; },
    mound: function () { return path('M3 26 C5 16 10 10 16 10 C22 10 27 16 29 26 Z', C.soil, 2.2) + line('M10 18 l2 2 M18 15 l2 -1 M21 21 l2 1', 1.6, '#6e4a30') + '<circle cx="6" cy="8" r="2" fill="' + C.soil + '"' + st(1.8) + '/>'; },
    pebble: function () { return el(13, 21, 10, 6.5, '#b9b2a6', 1.8) + el(21, 13, 7, 5, '#d3cdc2', 1.8) + line('M8 19 q3 -2 6 -1 M18 11 q2 -1.5 4 -1', 1.2, '#fff', '.7'); },
    twig: function () { return twigAt(4, 26, 28, 8, 3.6) + line('M15 18 L12 9', 5.6) + line('M15 18 L12 9', 2.2, C.twig) + leafAt(26, 7, .4, 50); },
    log: function () { return '<rect x="3" y="10" width="22" height="13" rx="2" fill="' + C.twig + '"' + st(2.2) + '/>' + el(25, 16.5, 5, 6.5, '#e3c19c', 2.2) + el(25, 16.5, 2.2, 3, 'none', 1.2) + line('M8 14 H16 M10 19 H19', 1.4, '#6e4a30'); },
    chewed: function () { return path('M10 4 H22 V9 C18 12 18 15 16 16 C14 15 14 12 10 9 Z', '#e3c19c', 2.2) + path('M10 28 H22 V23 C18 20 18 17 16 16 C14 17 14 20 10 23 Z', C.twig, 2.2) + path('M3 27 l3 -2 l1 3 Z M27 26 l3 1 l-2 3 Z', C.chip, 1.4); },
    chips: function () { return path('M5 20 L13 15 L15 20 L8 24 Z', C.chip, 1.6) + path('M17 9 L25 8 L24 13 L18 14 Z', C.chip, 1.6) + path('M18 22 L26 19 L27 24 L20 26 Z', '#d6ad7c', 1.6) + line('M7 21 l5 -3 M19 10.5 l4 -.5', .9, '#a8805a'); }
  };
  var TRACE_OWNER = { seed: 'bao', crumbs: 'bao', sunflower: 'bao', berry: 'bao', acorn: 'kacang', leaf: 'kacang', pinecone: 'kacang', mushroom: 'kacang', footprint: 'gali', hole: 'gali', mound: 'gali', pebble: 'gali', twig: 'kayu', log: 'kayu', chewed: 'kayu', chips: 'kayu' };
  function traceSVG(name, size) {
    var s = size || 32;
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="' + s + '" height="' + s + '" aria-hidden="true">' + (TRACES[name] || TRACES.seed)() + '</svg>';
  }
  var FUR = { hamster: C.hamster, squirrel: C.squirrel, molerat: C.molerat, beaver: C.beaver };

  /* ---------- trails: traces laid along a smooth path through given points ---------- */
  function spline(pts, n) {
    var out = [], P = [pts[0]].concat(pts, [pts[pts.length - 1]]);
    for (var i = 1; i < P.length - 2; i++) {
      var p0 = P[i - 1], p1 = P[i], p2 = P[i + 1], p3 = P[i + 2];
      for (var t = 0; t < 1; t += 1 / n) {
        var t2 = t * t, t3 = t2 * t;
        out.push([0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
          0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)]);
      }
    }
    out.push(pts[pts.length - 1]); return out;
  }
  function along(pts, spacing) {
    var s = spline(pts, 24), out = [], acc = 0, next = spacing / 2;
    for (var i = 1; i < s.length; i++) {
      var dx = s[i][0] - s[i - 1][0], dy = s[i][1] - s[i - 1][1], d = Math.sqrt(dx * dx + dy * dy);
      while (acc + d >= next && d > 0) { var t = (next - acc) / d; out.push({ x: s[i - 1][0] + dx * t, y: s[i - 1][1] + dy * t, a: Math.atan2(dy, dx) * 180 / Math.PI }); next += spacing; }
      acc += d;
    }
    return out;
  }
  var TRAIL = {
    footprints: { spacing: 17, draw: function (p, i, op) { var side = i % 2 ? 1 : -1, r = (p.a + 90) * Math.PI / 180; return printAt(p.x + Math.cos(r) * side * 6, p.y + Math.sin(r) * side * 6, .74, p.a + 90, '#8a5a3b', op); } },
    crumbs: { spacing: 14, draw: function (p, i, op) { var j = [[0, 0], [2, -3], [-2, 2], [3, 2]][i % 4]; return '<g opacity="' + op + '">' + crumb(p.x + j[0], p.y + j[1], [1.3, 1.6, 1.1, 1.4][i % 4], i * 47) + (i % 3 === 1 ? crumb(p.x - j[1] - 5, p.y + j[0] + 4, .9, i * 23) : '') + '</g>'; } },
    seeds: { spacing: 17, draw: function (p, i, op) { return '<g opacity="' + op + '">' + seedAt(p.x, p.y, .68, p.a + 90 + (i % 2 ? 25 : -25)) + '</g>'; } },
    acorns: { spacing: 26, draw: function (p, i, op) { return '<g opacity="' + op + '">' + (i % 3 === 2 ? leafAt(p.x, p.y, .6, p.a + 60) : acornAt(p.x, p.y, .74, (i % 2 ? 18 : -18))) + '</g>'; } },
    leaves: { spacing: 22, draw: function (p, i, op) { return '<g opacity="' + op + '">' + leafAt(p.x, p.y, .5, p.a + (i % 2 ? 70 : 110), i % 4 === 3 ? '#e9a53a' : C.leaf) + '</g>'; } },
    chips: { spacing: 15, draw: function (p, i, op) { return '<g opacity="' + op + '" transform="translate(' + (p.x - 8) + ' ' + (p.y - 8) + ') rotate(' + (i * 61) + ' 8 8) scale(.5)">' + TRACES.chips() + '</g>'; } }
  };
  /* opts: {kind, points: [[x,y]...], width, height, spacing, fade (0..1: start opacity), done (0..1 share drawn at full strength)} */
  function trailSVG(o) {
    var k = TRAIL[o.kind] ? o.kind : 'footprints', T = TRAIL[k], pts = along(o.points, o.spacing || T.spacing), n = pts.length, out = '';
    var fade = o.fade == null ? .5 : o.fade, done = o.done == null ? 1 : o.done;
    pts.forEach(function (p, i) { var f = n > 1 ? i / (n - 1) : 1, op = f > done + 1e-6 ? .22 : fade + (1 - fade) * (done ? f / done : 1); out += '<g class="bh-trail__step" style="--i:' + i + '">' + T.draw(p, i, Math.min(1, op).toFixed(2)) + '</g>'; });
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + o.width + ' ' + o.height + '" width="' + o.width + '" height="' + o.height + '" aria-hidden="true" overflow="visible">' + out + '</svg>';
  }
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
  function raw(tag, cls, html, style, extra) { return h(tag, Object.assign({ className: cls, style: style, dangerouslySetInnerHTML: { __html: html } }, extra || {})); }

  /* ---------- cast and traces ---------- */
  function Mascot(p) {
    var size = p.size || 96;
    return raw('span', cx('bh-mascot', p.bounce && 'bh-mascot--bounce', p.className), mascotSVG(p.character || 'bao', p.mood || 'happy', p.label), { width: size, height: size });
  }
  function Trace(p) { var s = p.size || 32; return raw('span', cx('bh-trace', p.className), traceSVG(p.name, s), Object.assign({ width: s, height: s }, p.style || {})); }

  /* an animal peeking over the top edge (or around the right edge) of whatever it wraps, paws on the edge */
  function pawsSVG(who, n, size) {
    var paw = FUR[who] || C.hamster, w = n === 1 ? 26 : 60;
    var body = n === 1 ? el(13, 7, 9, 5.5, paw, 2.4) + line('M9 4 v3 M13 3.5 v3 M17 4 v3', 1.1, INK, '.7') : el(14, 7, 9, 5.5, paw, 2.4) + el(46, 7, 9, 5.5, paw, 2.4) + line('M10 4 v3 M14 3.5 v3 M18 4 v3 M42 4 v3 M46 3.5 v3 M50 4 v3', 1.1, INK, '.7');
    return '<svg viewBox="0 0 ' + w + ' 14" width="' + Math.round(size * w / 120) + '" height="' + Math.round(size * .12) + '" aria-hidden="true">' + body + '</svg>';
  }
  function Peek(p) {
    var size = p.size || 72, who = ALIAS[p.character] || p.character || 'hamster';
    if (p.edge === 'side') {
      var top = p.offset != null ? p.offset : 12;
      return h('div', { className: cx('bh-peek', 'bh-peek--side', p.className), style: { paddingRight: Math.round(size * .5) } },
        h('span', { className: 'bh-peek__animal', style: { width: size, height: size, right: 0, top: top } }, h(Mascot, { character: who, mood: p.mood, size: size })),
        h('div', { className: 'bh-peek__body' }, p.children),
        raw('span', 'bh-peek__paws', pawsSVG(who, 1, size), { right: Math.round(size * .5) - Math.round(size * .1), top: top + Math.round(size * .6) }));
    }
    var t = Math.round(size * 0.74), side = p.side || 'right', pos = {}; pos[side] = p.offset != null ? p.offset : 24;
    var pawPos = { top: t - Math.round(size * 0.06) }; pawPos[side] = pos[side] + size * 0.25;
    return h('div', { className: cx('bh-peek', p.className), style: { paddingTop: t } },
      h('span', { className: 'bh-peek__animal', style: Object.assign({ width: size, height: size }, pos) }, h(Mascot, { character: who, mood: p.mood, size: size })),
      h('div', { className: 'bh-peek__body' }, p.children),
      raw('span', 'bh-peek__paws', pawsSVG(who, 2, size), pawPos));
  }

  /* ---------- habitats: a header band per animal, with ground, props and its resident ---------- */
  function tuft(x, y, s) { s = s || 1; return '<path class="hb-tuft" d="M' + x + ' ' + y + ' l' + (-4 * s) + ' ' + (-9 * s) + ' M' + x + ' ' + y + ' l' + (1 * s) + ' ' + (-11 * s) + ' M' + x + ' ' + y + ' l' + (5 * s) + ' ' + (-8 * s) + '"/>'; }
  function cloud(x, y, s) { return '<path class="hb-cloud" transform="translate(' + x + ' ' + y + ') scale(' + s + ')" d="M0 16 C-2 8 6 4 12 7 C14 0 26 -2 30 6 C38 4 44 10 41 16 Z"/>'; }
  function tr(name, x, y, s, rot) { return '<g transform="translate(' + x + ' ' + y + ') rotate(' + (rot || 0) + ' 16 16) scale(' + (s || 1) + ')">' + TRACES[name]() + '</g>'; }
  var HAB = {
    meadow: { who: 'hamster', props: function () {
      return '<path class="hb-stem" d="M58 150 C56 120 60 90 56 64 M92 150 C94 126 90 104 92 86"/>' +
        '<path class="hb-leaf" d="M57 112 C46 104 38 108 34 112 C42 118 50 118 57 112 Z"/><path class="hb-leaf" d="M93 120 C104 112 112 116 116 120 C108 126 100 126 93 120 Z"/><path class="hb-leaf" d="M57 92 C66 86 72 88 76 92 C70 97 63 97 57 92 Z"/>' +
        '<g transform="translate(36 42) scale(1.25)">' + TRACES.sunflower() + '</g><g transform="translate(76 68) scale(.9)">' + TRACES.sunflower() + '</g>' +
        tr('berry', 6, 112, .9) + tuft(30, 140) + tuft(118, 142, .8) + tuft(196, 140) +
        seedAt(150, 132, .7, 60) + seedAt(166, 138, .7, -30) + crumb(178, 134, 1, 20) + crumb(140, 138, .8, 70); },
      ground: '<path class="hb-grass hb-ground" d="M0 18 C60 2 120 2 200 14 C280 26 340 26 400 10 V48 H0 Z"/><path class="hb-edge" d="M0 18 C60 2 120 2 200 14 C280 26 340 26 400 10"/>',
      far: '<path class="hb-far" d="M0 30 C60 6 140 10 200 26 C260 40 330 8 400 20 V60 H0 Z"/>' },
    oak: { who: 'squirrel', props: function () {
      return '<path class="hb-bark" d="M220 4 C176 10 146 16 116 30 C102 36 88 36 72 32"/><path class="hb-bark hb-bark--thin" d="M146 18 C138 8 128 2 116 -2 M100 33 C96 40 96 46 98 52"/>' +
        leafAt(70, 30, 1.1, -40) + leafAt(106, 40, 1, 30) + leafAt(158, 14, 1, -10) + leafAt(132, 30, .9, 150) + leafAt(186, 10, .9, 40) +
        line('M98 52 L98 58', 1.8) + acornAt(98, 66, .9, 0) + acornAt(18, 136, .8, -20) + acornAt(182, 138, .8, 25) +
        leafAt(36, 80, .7, 50, '#e9a53a') + leafAt(150, 96, .6, -30) + tr('mushroom', 132, 118, .8) + tuft(40, 142) + tuft(200, 142, .8); },
      ground: '<path class="hb-grass hb-ground" d="M0 14 C80 26 160 26 240 12 C300 2 360 4 400 16 V48 H0 Z"/><path class="hb-edge" d="M0 14 C80 26 160 26 240 12 C300 2 360 4 400 16"/>',
      far: '<path class="hb-far" d="M0 26 C80 10 140 14 220 30 C290 44 350 18 400 24 V60 H0 Z"/>' },
    burrow: { who: 'molerat', props: function () {
      return tr('mound', 150, 104, 1.1) + tr('pebble', 18, 118, .7) +
        printAt(8, 132, .55, 75, C.soil, '.85') + printAt(24, 126, .55, 95, C.soil, '.85') + printAt(40, 132, .55, 75, C.soil, '.85') + printAt(56, 126, .55, 95, C.soil, '.85') + tuft(196, 132, .8); },
      ground: '<path class="hb-soil" d="M0 12 C100 4 200 4 300 10 C340 13 370 13 400 10 V48 H0 Z"/><path class="hb-fringe" d="M0 12 C100 4 200 4 300 10 C340 13 370 13 400 10"/><path class="hb-root" d="M60 12 C62 22 56 30 60 40 M60 24 C66 28 70 34 68 42 M250 9 C248 20 254 28 250 40"/><path class="hb-tunnel-line" d="M20 34 C80 28 140 40 220 32 C280 26 330 36 380 30"/>',
      far: '' },
    river: { who: 'beaver', props: function () {
      var logs = '';
      [[136, 118], [166, 118], [151, 100], [181, 100], [166, 82]].forEach(function (q) { logs += '<g transform="translate(' + (q[0] - 16) + ' ' + (q[1] - 16) + ') scale(1.3)">' + TRACES.log() + '</g>'; });
      return '<path class="hb-stem" d="M14 150 C14 120 16 100 14 80 M24 150 C24 126 26 110 26 92 M110 150 C110 130 112 116 110 104"/>' +
        el(14, 76, 3.6, 10, '#8a5a3b', 1.8) + el(26, 88, 3.4, 9, '#8a5a3b', 1.8) + el(110, 100, 3, 8, '#8a5a3b', 1.8) +
        logs + tr('chips', 112, 120, .7) + tr('pebble', 186, 128, .6); },
      ground: '<path class="hb-water hb-ground" d="M0 16 C50 8 100 8 150 16 C200 24 250 24 300 16 C340 10 370 10 400 14 V48 H0 Z"/><path class="hb-edge" d="M0 16 C50 8 100 8 150 16 C200 24 250 24 300 16 C340 10 370 10 400 14"/><path class="hb-ripple" d="M30 30 q10 -6 20 0 t20 0 M180 36 q10 -6 20 0 t20 0 M300 28 q10 -6 20 0 t20 0"/><ellipse class="hb-lily" cx="120" cy="28" rx="16" ry="4.5"/>',
      far: '<path class="hb-far" d="M0 34 C70 20 150 24 220 32 C300 40 350 24 400 28 V60 H0 Z"/>' }
  };
  function Habitat(p) {
    var kind = HAB[p.kind] ? p.kind : 'meadow', hab = HAB[kind], who = ALIAS[p.character] || p.character || hab.who;
    return h('div', { className: cx('bh-habitat', 'bh-habitat--' + kind, p.className), style: p.style },
      hab.far ? raw('span', 'bh-habitat__far', '<svg viewBox="0 0 400 60" preserveAspectRatio="none" width="100%" height="60" aria-hidden="true">' + hab.far + '</svg>') : null,
      kind !== 'burrow' ? raw('span', 'bh-habitat__clouds', '<svg viewBox="0 0 160 40" width="160" height="40" aria-hidden="true">' + cloud(4, 8, .9) + cloud(92, 2, .7) + '</svg>') : null,
      raw('span', 'bh-habitat__props', '<svg viewBox="0 0 210 150" width="210" height="150" aria-hidden="true">' + hab.props() + '</svg>'),
      raw('span', 'bh-habitat__ground', '<svg viewBox="0 0 400 48" preserveAspectRatio="none" width="100%" height="48" aria-hidden="true">' + hab.ground + '</svg>'),
      p.character === false ? null : h('span', { className: 'bh-habitat__resident' }, h(Mascot, { character: who, mood: p.mood || 'happy', size: p.size || 96, bounce: p.bounce })),
      h('div', { className: 'bh-habitat__content' }, p.children));
  }
  function Backdrop(p) {
    return h('div', { className: cx('bh-backdrop', 'bh-backdrop--' + (p.pattern || 'dots'), p.className), style: p.style }, p.children);
  }
  function Divider(p) { return h('div', { className: cx('bh-divider', 'bh-divider--' + (p.kind || 'seeds'), p.className), role: 'separator' }); }

  /* ---------- icons ---------- */
  var ICONS = {
    home: 'M4 11 L12 4 L20 11 V20 H14 V14 H10 V20 H4 Z',
    plus: 'M12 5 V19 M5 12 H19',
    chart: 'M5 19 V11 M12 19 V5 M19 19 V14',
    gear: 'M12 9 A3 3 0 1 0 12 15 A3 3 0 1 0 12 9 Z M12 3 V5.5 M12 18.5 V21 M3 12 H5.5 M18.5 12 H21 M5.6 5.6 L7.4 7.4 M16.6 16.6 L18.4 18.4 M5.6 18.4 L7.4 16.6 M16.6 7.4 L18.4 5.6',
    camera: 'M4 8 H8 L9.5 5.5 H14.5 L16 8 H20 V19 H4 Z M12 10 A3.5 3.5 0 1 0 12 17 A3.5 3.5 0 1 0 12 10 Z',
    bowl: 'M3.5 11 H20.5 C20.5 16 16.5 19.5 12 19.5 C7.5 19.5 3.5 16 3.5 11 Z M9 8 C9 6.5 10 6 10 4.5 M14 8 C14 6.5 15 6 15 4.5',
    wallet: 'M4 7 H18 A2 2 0 0 1 20 9 V18 A2 2 0 0 1 18 20 H6 A2 2 0 0 1 4 18 Z M4 7 L15 4 V7 M15.5 13.5 H16.5',
    search: 'M10.5 4 A6.5 6.5 0 1 0 10.5 17 A6.5 6.5 0 1 0 10.5 4 Z M15.5 15.5 L20 20',
    'arrow-up': 'M12 19 V5 M6 11 L12 5 L18 11',
    'arrow-down': 'M12 5 V19 M6 13 L12 19 L18 13',
    check: 'M5 12.5 L10 17.5 L19 7',
    calendar: 'M5 6 H19 V20 H5 Z M5 10 H19 M9 3.5 V7.5 M15 3.5 V7.5'
  };
  function Icon(p) {
    var s = p.size || 24;
    return h('svg', { className: cx('bh-icon', p.className), width: s, height: s, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': p.label ? undefined : true, 'aria-label': p.label, role: p.label ? 'img' : undefined },
      h('path', { d: ICONS[p.name] || ICONS.plus }));
  }

  /* ---------- controls ---------- */
  function Button(p) {
    var rest = Object.assign({}, p); delete rest.variant; delete rest.size; delete rest.icon; delete rest.className;
    return h('button', Object.assign({ type: 'button' }, rest, { className: cx('bh-btn', 'bh-btn--' + (p.variant || 'primary'), p.size === 'sm' && 'bh-btn--sm', !p.children && 'bh-btn--icon', p.className) }),
      p.icon ? h(Icon, { name: p.icon, size: p.size === 'sm' ? 18 : 20 }) : null, p.children);
  }
  function Chip(p) {
    return h('button', { type: 'button', className: cx('bh-chip', p.selected && 'is-selected', p.className), 'aria-pressed': !!p.selected, onClick: p.onClick },
      p.selected ? h(Icon, { name: 'check', size: 16 }) : null, p.children);
  }
  function Field(p) {
    var id = p.id || ('bh-f-' + String(p.label || '').replace(/\W+/g, '-').toLowerCase());
    return h('label', { className: cx('bh-field', p.error && 'has-error', p.className), htmlFor: id },
      h('span', { className: 'bh-field__label' }, p.label),
      h('span', { className: 'bh-field__box' },
        p.prefix ? h('span', { className: 'bh-field__affix' }, p.prefix) : null,
        h('input', { id: id, className: 'bh-field__input', placeholder: p.placeholder, defaultValue: p.defaultValue, inputMode: p.inputMode, type: p.type || 'text' }),
        p.suffix ? h('span', { className: 'bh-field__affix' }, p.suffix) : null),
      p.error ? h('span', { className: 'bh-field__msg' }, p.error) : p.hint ? h('span', { className: 'bh-field__hint' }, p.hint) : null);
  }

  /* ---------- containers ---------- */
  function Card(p) {
    var card = h('section', { className: cx('bh-card', p.tint && 'bh-card--tint', p.nibbled && 'bh-card--nibbled', p.className) },
      p.title || p.action ? h('header', { className: 'bh-card__head' }, h('h3', { className: 'bh-card__title' }, p.title), p.action || null) : null,
      p.children);
    if (!p.nibbled) return card;
    return h('div', { className: 'bh-nibble' }, card, h(Trace, { name: 'crumbs', size: 26, className: 'bh-nibble__crumbs' }));
  }
  function ListRow(p) {
    return h('div', { className: cx('bh-row', p.className) },
      h('span', { className: 'bh-row__tile', style: p.tileColor ? { background: 'var(--' + p.tileColor + ')' } : null }, p.leading || (p.trace ? h(Trace, { name: p.trace, size: 30 }) : p.icon ? h(Icon, { name: p.icon, size: 22 }) : null)),
      h('span', { className: 'bh-row__text' }, h('span', { className: 'bh-row__title' }, p.title), p.subtitle ? h('span', { className: 'bh-row__sub' }, p.subtitle) : null),
      p.amount != null ? h('span', { className: cx('bh-row__amount', p.tone && 'is-' + p.tone) }, p.amount) : null);
  }
  function BottomNav(p) {
    var nav = h('nav', { className: 'bh-nav', 'aria-label': 'Main' },
      (p.items || []).map(function (it, i) {
        if (it.fab) return h('button', { key: i, type: 'button', className: 'bh-nav__fab', 'aria-label': it.label }, h(Icon, { name: it.icon || 'plus', size: 26 }));
        var on = it.id === p.active;
        return h('a', { key: i, href: it.href || '#', className: cx('bh-nav__item', on && 'is-active'), 'aria-current': on ? 'page' : undefined },
          h('span', { className: 'bh-nav__pill' }, h(Icon, { name: it.icon, size: 22 })), h('span', { className: 'bh-nav__label' }, it.label));
      }));
    return p.peek ? h(Peek, { character: p.peek, size: 64, side: 'left', offset: 24, mood: p.peekMood }, nav) : nav;
  }

  /* ---------- data ---------- */
  function Meter(p) {
    var pct = Math.max(0, Math.min(1, (p.value || 0) / (p.max || 1)));
    var over = (p.value || 0) > (p.max || 1);
    return h('div', { className: cx('bh-meter', over && 'is-over', p.className) },
      h('div', { className: 'bh-meter__top' }, h('span', { className: 'bh-meter__label' }, p.label),
        h('span', { className: 'bh-meter__value' }, p.valueText || (p.value + ' / ' + p.max), over ? h('span', { className: 'bh-meter__over' }, ' over') : null)),
      h('div', { className: 'bh-meter__rail' },
        h('div', { className: 'bh-meter__track', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': p.max, 'aria-valuenow': p.value, 'aria-label': p.label },
          h('div', { className: 'bh-meter__fill', style: { width: (pct * 100) + '%', background: 'var(--' + (over ? 'tomato' : (p.color || 'accent')) + ')' } })),
        p.cap ? h(Trace, { name: p.cap, size: 24, className: 'bh-meter__cap', style: { left: (pct * 100) + '%' } }) : null));
  }
  /* progress ring. variant 'sunflower' (petals open as the day fills, makan), 'wreath' (oak leaves, money), or plain */
  function Ring(p) {
    var v = p.variant, size = p.size || (v === 'sunflower' ? 208 : v === 'wreath' ? 196 : 168), c = size / 2;
    var pct = Math.max(0, Math.min(1, (p.value || 0) / (p.max || 1))), kids = [], rp, i;
    if (v === 'sunflower') {
      var N = 22, on = Math.round(pct * N), hr = size * 0.27; rp = size * 0.375;
      for (i = 0; i < N; i++) kids.push(h('ellipse', { key: 'p' + i, className: cx('bh-petal', i < on && 'is-on'), cx: c, cy: c - rp, rx: size * 0.046, ry: size * 0.11, transform: 'rotate(' + (i * 360 / N) + ' ' + c + ' ' + c + ')' }));
      kids.push(h('circle', { key: 'hd', className: 'bh-seedhead', cx: c, cy: c, r: hr }));
      for (i = 20; i < 220; i++) { var rr = hr * Math.sqrt(i / 220); if (rr < hr * 0.74) continue; var th = i * 2.39996; kids.push(h('circle', { key: 's' + i, className: 'bh-seedhead__seed', cx: c + rr * Math.cos(th), cy: c + rr * Math.sin(th), r: size * 0.0085 })); }
    } else if (v === 'wreath') {
      var L = 26, lon = Math.round(pct * L); rp = size * 0.4;
      kids.push(h('circle', { key: 'br', className: 'bh-wreath__branch', cx: c, cy: c, r: rp }));
      for (i = 0; i < L; i++) {
        var ang = -90 + (i + .5) * 360 / L, rad = ang * Math.PI / 180, out = i % 2 ? 5 : -5;
        kids.push(h('path', { key: 'l' + i, className: cx('bh-wleaf', i < lon && 'is-on'), d: 'M0 -11 C3 -9 2 -7 4.5 -6.5 C7 -6 6 -3 4.5 -2 C8 -1.5 8 2 5 2.5 C7 4.5 5 7.5 3 6.5 C2.5 9 1 10 0 11 C-1 10 -2.5 9 -3 6.5 C-5 7.5 -7 4.5 -5 2.5 C-8 2 -8 -1.5 -4.5 -2 C-6 -3 -7 -6 -4.5 -6.5 C-2 -7 -3 -9 0 -11 Z',
          transform: 'translate(' + (c + (rp + out) * Math.cos(rad)) + ' ' + (c + (rp + out) * Math.sin(rad)) + ') rotate(' + (ang + (i % 2 ? 125 : 55)) + ') scale(' + (size / 165) + ')' }));
      }
    } else {
      var sw = 16, r = (size - sw - 4) / 2, Cc = 2 * Math.PI * r; rp = r;
      kids.push(h('circle', { key: 't', cx: c, cy: c, r: r, className: 'bh-ring__track', strokeWidth: sw }));
      kids.push(h('circle', { key: 'f', cx: c, cy: c, r: r, className: 'bh-ring__fill', strokeWidth: sw, strokeDasharray: Cc, strokeDashoffset: Cc * (1 - pct), transform: 'rotate(-90 ' + c + ' ' + c + ')', style: p.color ? { stroke: 'var(--' + p.color + ')' } : null }));
    }
    var deco = v === 'wreath' ? raw('span', 'bh-ring__deco', '<svg viewBox="0 0 60 30" width="60" height="30">' + acornAt(20, 14, 1, -20) + acornAt(40, 14, 1, 20) + '</svg>', { left: c - 30, top: c + rp - 14 }) : null;
    var a2 = -Math.PI / 2 + pct * 2 * Math.PI, isAnimal = ALIAS[p.cap] || CAST[p.cap], capSize = p.capSize || (isAnimal ? 52 : 30);
    return h('div', { className: cx('bh-ring', v && 'bh-ring--' + v), style: { width: size, height: size } },
      h('svg', { width: size, height: size, viewBox: '0 0 ' + size + ' ' + size, 'aria-hidden': true }, kids), deco,
      h('div', { className: 'bh-ring__center', style: { width: size, height: size } }, p.children),
      p.cap ? h('span', { className: 'bh-ring__cap', style: { left: c + rp * Math.cos(a2) - capSize / 2, top: c + rp * Math.sin(a2) - capSize * (isAnimal ? 0.78 : 0.5) } },
        isAnimal ? h(Mascot, { character: p.cap, mood: p.capMood || 'joy', size: capSize }) : h(Trace, { name: p.cap, size: capSize })) : null);
  }
  /* a squirrel's buried stash: one per sinking fund, acorns piled to the share of its target */
  function Stash(p) {
    var pct = Math.max(0, Math.min(1, (p.value || 0) / (p.max || 1))), n = Math.round(pct * 15), rows = [5, 4, 3, 2, 1], out = '', k = 0;
    rows.forEach(function (cnt, ri) { for (var i = 0; i < cnt; i++) { if (k++ < n) out += acornAt(80 - (cnt - 1) * 9 + i * 18, 94 - ri * 14, 0.95, ((i + ri) % 2 ? 8 : -8)); } });
    var svg = '<svg viewBox="0 0 160 116" width="100%" aria-hidden="true">' +
      '<path class="hb-soil" d="M0 10 H160 V100 Q160 116 144 116 H16 Q0 116 0 100 Z"/>' +
      '<path class="hb-fringe" d="M0 10 H160"/><path class="hb-grass-blades" d="M14 10 l-3 -7 M18 10 l1 -8 M120 10 l-2 -6 M126 10 l2 -8 M150 10 l1 -6"/>' +
      '<path class="hb-tunnel" d="M118 40 C126 30 132 20 136 8"/>' +
      '<path class="hb-chamber" d="M26 108 C22 62 46 30 80 30 C114 30 138 62 134 108 Z"/>' + out +
      (n === 0 ? '<g transform="translate(64 80)">' + TRACES.footprint() + '</g>' : '') + '</svg>';
    return h('div', { className: cx('bh-stash', p.className) }, raw('div', 'bh-stash__art', svg),
      h('div', { className: 'bh-stash__label' }, h('span', { className: 'bh-stash__name' }, p.name), h('span', { className: 'bh-stash__value' }, p.valueText), p.targetText ? h('span', { className: 'bh-stash__target' }, p.targetText) : null));
  }

  /* ---------- wayfinding: trails lead the eye to the next thing that matters ---------- */
  function useWidth(fallback) {
    var ref = React.useRef(null), s = React.useState(fallback), w = s[0], set = s[1];
    React.useLayoutEffect(function () {
      if (!ref.current) return;
      var first = Math.round(ref.current.getBoundingClientRect().width); if (first) set(first);
      if (!window.ResizeObserver) return;
      var ro = new ResizeObserver(function (e) { var nw = Math.round(e[0].contentRect.width); if (nw) set(nw); });
      ro.observe(ref.current); return function () { ro.disconnect(); };
    }, []);
    return [ref, w];
  }
  function Trail(p) { return raw('span', cx('bh-trail', p.animate && 'bh-trail--animate', p.className), trailSVG(p), p.style); }
  /* a short trail across the gap between two stacked blocks, from one side to the other */
  function TrailGap(p) {
    var m = useWidth(320), w = m[1], hgt = p.height || 52, f = (p.from != null ? p.from : .2) * w, t = (p.to != null ? p.to : .8) * w, d = t - f;
    return h('div', { ref: m[0], className: cx('bh-trailgap', p.animate && 'bh-trail--animate', p.className), style: { height: hgt }, 'aria-hidden': true,
      dangerouslySetInnerHTML: { __html: trailSVG({ kind: p.kind, width: w, height: hgt, fade: p.fade, done: p.done, points: [[f, 4], [f + d * .35, hgt * .38], [t - d * .35, hgt * .62], [t, hgt - 4]] }) } });
  }
  var STEP_MARK = { crumbs: 'crumbs', seeds: 'seed', footprints: 'footprint', acorns: 'acorn', leaves: 'leaf', chips: 'chips' };
  /* stops along one trail: what's done (a trace), where you are (the animal), what's next (an empty stop) */
  function TrailSteps(p) {
    var kind = p.kind || 'crumbs', steps = p.steps || [], cur = -1, out = [];
    steps.forEach(function (s, i) { if (cur < 0 && s.state === 'current') cur = i; });
    steps.forEach(function (s, i) {
      var state = s.state || (cur < 0 || i < cur ? 'done' : i === cur ? 'current' : 'todo');
      if (i > 0) out.push(h('div', { key: 'l' + i, className: 'bh-steps__link', 'aria-hidden': true, dangerouslySetInnerHTML: { __html: trailSVG({ kind: kind, width: 48, height: 34, fade: state === 'todo' ? .2 : .55, done: state === 'todo' ? 0 : 1, points: [[24, 0], [18, 11], [30, 23], [24, 34]] }) } }));
      out.push(h('div', { key: 's' + i, className: cx('bh-step', 'is-' + state), 'aria-current': state === 'current' ? 'step' : undefined },
        h('span', { className: 'bh-step__mark' }, state === 'current' ? h(Mascot, { character: p.character || TRACE_OWNER[STEP_MARK[kind]], mood: s.mood || 'happy', size: 50 }) : state === 'done' ? h(Trace, { name: STEP_MARK[kind] || 'crumbs', size: 26 }) : null),
        h('span', { className: 'bh-step__body' }, h('span', { className: 'bh-step__title' }, s.title), s.sub ? h('span', { className: 'bh-step__sub' }, s.sub) : null),
        s.aside ? h('span', { className: 'bh-step__aside' }, s.aside) : null));
    });
    return h('div', { className: cx('bh-steps', p.className) }, out);
  }
  /* Gali's tunnel: history as chambers along one underground tunnel, footprints between them */
  function Tunnel(p) {
    var items = p.items || [];
    return h('div', { className: cx('bh-tunnel', p.className) }, items.map(function (it, i) {
      var last = i === items.length - 1, prints = '';
      if (!last) along([[32, 46], [24, 70], [40, 96], [32, 124]], 15).forEach(function (q, k) { var r = (q.a + 90) * Math.PI / 180, sd = k % 2 ? 1 : -1; prints += '<g class="bh-tunnel__print">' + printAt(q.x + Math.cos(r) * sd * 4, q.y + Math.sin(r) * sd * 4, .5, q.a + 90) + '</g>'; });
      return h('div', { key: i, className: 'bh-tunnel__row' },
        raw('span', 'bh-tunnel__rail', '<svg viewBox="0 0 64 124" preserveAspectRatio="xMidYMin meet" width="64" height="100%" overflow="visible" aria-hidden="true">' +
          (last ? '' : '<path class="hb-tunnel" d="M32 40 C24 64 42 92 32 130 V600"/>') + prints +
          '<ellipse class="hb-chamber" cx="32" cy="24" rx="24" ry="17"/></svg>'),
        h('span', { className: 'bh-tunnel__day' }, h('span', { className: 'bh-tunnel__num' }, it.day), h('span', { className: 'bh-tunnel__mon' }, it.month)),
        h('div', { className: 'bh-tunnel__body' }, it.title ? h('span', { className: 'bh-tunnel__title' }, it.title) : null, it.children));
    }));
  }
  function Breadcrumbs(p) {
    var items = p.items || [], sep = p.kind === 'footprints' ? 'footprint' : p.kind === 'acorns' ? 'acorn' : 'crumbs';
    return h('nav', { className: cx('bh-crumbs', p.className), 'aria-label': 'Breadcrumb' }, h('ol', null, items.map(function (it, i) {
      var last = i === items.length - 1;
      return h('li', { key: i }, i > 0 ? h(Trace, { name: sep, size: 16, className: 'bh-crumbs__sep' }) : null,
        last ? h('span', { 'aria-current': 'page' }, it.label) : h('a', { href: it.href || '#' }, it.label));
    })));
  }
  function Loader(p) {
    var kind = p.kind || 'footprints', T = TRAIL[kind] || TRAIL.footprints, items = '';
    for (var i = 0; i < 7; i++) items += '<g class="bh-loader__print" style="animation-delay:' + (i * .2).toFixed(2) + 's">' + T.draw({ x: 10 + i * 16, y: 14, a: 0 }, i, 1) + '</g>';
    return h('div', { className: 'bh-loader', role: 'status' }, raw('span', 'bh-loader__trail', '<svg viewBox="0 0 120 28" width="120" height="28" aria-hidden="true" overflow="visible">' + items + '</svg>'), p.label ? h('span', { className: 'bh-loader__label' }, p.label) : null);
  }

  /* ---------- moments ---------- */
  function EmptyState(p) {
    return h('div', { className: cx('bh-empty', p.className) },
      h(Mascot, { character: p.character || 'bao', mood: p.mood || 'sleepy', size: p.size || 112 }),
      h('h3', { className: 'bh-empty__title' }, p.title),
      p.body ? h('p', { className: 'bh-empty__body' }, p.body) : null,
      p.action || null);
  }
  function Toast(p) {
    return h('div', { className: cx('bh-toast', p.className), role: 'status' },
      h('span', { className: 'bh-toast__bub' }, h(Mascot, { character: p.character || 'bao', mood: p.mood || 'joy', size: 40 })),
      h('span', { className: 'bh-toast__text' }, p.children),
      p.action || null);
  }
  /* ---------- the world: all four habitats in one landscape ---------- */
  function placed(who, mood, x, y, s) { return '<svg x="' + x + '" y="' + y + '" width="' + s + '" height="' + s + '" viewBox="0 0 120 120">' + CAST[who](mood) + '</svg>'; }
  function trailIn(kind, pts, fade) { var T = TRAIL[kind], out = '', q = along(pts, T.spacing), n = q.length; q.forEach(function (p, i) { out += T.draw(p, i, (fade + (1 - fade) * i / Math.max(1, n - 1)).toFixed(2)); }); return out; }
  function worldSVG() {
    var acorns = '', k = 0; [5, 4, 3].forEach(function (cnt, ri) { for (var i = 0; i < cnt; i++) acorns += acornAt(130 - (cnt - 1) * 9 + i * 18, 280 - ri * 13, .9, (k++ % 2 ? 8 : -8)); });
    var logs = ''; [[836, 214], [872, 214], [908, 214], [854, 192], [890, 192], [872, 170]].forEach(function (q) { logs += tr('log', q[0], q[1], 1.3); });
    return '<svg viewBox="0 0 960 300" width="100%" aria-hidden="true" class="bh-world">' +
      '<circle class="hb-sun" cx="640" cy="54" r="28"/>' + cloud(300, 30, 1.4) + cloud(720, 60, 1.1) + cloud(470, 14, .9) +
      '<path class="hb-far" d="M0 196 C120 150 260 160 380 186 C500 210 600 150 760 168 C860 178 920 172 960 180 V214 H0 Z"/>' +
      '<path class="hb-soil" d="M0 210 H960 V300 H0 Z"/>' +
      '<path class="hb-root" d="M118 214 C110 236 96 244 86 262 M146 214 C156 232 170 238 178 254 M128 214 C130 230 126 240 130 250"/>' +
      '<path class="hb-tunnel" d="M352 240 C336 262 270 272 206 262 M352 240 C380 272 460 268 540 258 C580 252 610 262 640 272 M640 272 C700 284 760 276 800 262"/>' +
      '<path class="hb-chamber" d="M80 298 C76 258 100 238 130 238 C160 238 184 258 180 298 Z"/>' + acorns +
      '<path class="hb-chamber" d="M600 298 C598 276 616 264 640 264 C664 264 682 276 680 298 Z"/>' + seedAt(622, 284, .8, 30) + seedAt(640, 288, .8, -20) + seedAt(656, 283, .8, 60) + tr('berry', 626, 264, .6) +
      tr('pebble', 420, 270, .8) + tr('pebble', 760, 286, .6) + tr('pebble', 40, 250, .6) +
      '<path class="hb-grass" d="M0 204 C120 192 240 196 360 204 C480 212 560 196 690 200 L708 214 H0 Z"/>' +
      '<path class="hb-water" d="M690 200 C770 204 860 196 960 202 V300 H690 C694 270 700 236 690 200 Z"/>' +
      '<path class="hb-ripple" d="M730 236 q12 -7 24 0 t24 0 M800 262 q12 -7 24 0 t24 0 M900 248 q12 -7 24 0 t24 0"/><ellipse class="hb-lily" cx="790" cy="214" rx="22" ry="6"/>' +
      logs + tr('chips', 812, 188, .8) +
      '<path class="hb-stem" d="M700 206 C700 176 702 156 700 134 M712 206 C712 182 714 166 714 150"/>' + el(700, 130, 4, 11, '#8a5a3b', 2) + el(714, 146, 3.6, 10, '#8a5a3b', 2) +
      '<path class="hb-bark-fill" d="M110 210 C116 160 116 120 112 70 H148 C144 120 144 160 150 210 Z"/>' +
      '<path class="hb-bark" d="M140 120 C170 112 200 112 236 116"/>' +
      '<path class="hb-canopy" d="M60 80 C40 40 90 6 130 18 C170 0 230 30 214 70 C240 96 200 118 170 104 C150 120 110 118 96 104 C60 116 36 100 60 80 Z"/>' +
      leafAt(88, 52, 1, -30) + leafAt(190, 50, 1, 30) + leafAt(130, 76, .9, 10) + leafAt(156, 34, .8, -20) +
      line('M206 118 V132', 2) + acornAt(206, 142, .9, 0) + tr('mushroom', 160, 186, .8) + tr('mushroom', 182, 192, .55) + acornAt(76, 204, .8, 30) + leafAt(250, 190, .6, 70, '#e9a53a') +
      placed('squirrel', 'happy', 150, 32, 90) +
      placed('molerat', 'wow', 300, 138, 88) +
      trailIn('footprints', [[384, 206], [410, 200], [440, 206], [468, 200]], .35) +
      '<path class="hb-stem" d="M560 204 C558 170 562 140 558 116 M596 206 C598 180 594 160 598 140"/>' +
      tr('sunflower', 534, 76, 1.5) + tr('sunflower', 578, 110, 1.15) + tr('berry', 640, 176, 1) +
      placed('hamster', 'joy', 470, 106, 100) + seedAt(600, 200, .7, 70) + seedAt(456, 200, .7, -20) + crumb(616, 204, 1, 30) +
      placed('beaver', 'happy', 720, 102, 104) +
      '</svg>';
  }
  function World(p) { return raw('div', cx('bh-world-wrap', p && p.className), worldSVG()); }

  window.Burrow = Object.assign(window.Burrow || {}, {
    Mascot: Mascot, Habitat: Habitat, Trace: Trace, Peek: Peek, Trail: Trail, TrailGap: TrailGap, TrailSteps: TrailSteps, Tunnel: Tunnel, Breadcrumbs: Breadcrumbs, Divider: Divider, Ring: Ring, Meter: Meter, Stash: Stash, Card: Card, ListRow: ListRow,
    BottomNav: BottomNav, Button: Button, Chip: Chip, Field: Field, Loader: Loader, EmptyState: EmptyState, Toast: Toast, Backdrop: Backdrop, Icon: Icon, World: World,
    mascotSVG: mascotSVG, traceSVG: traceSVG, trailSVG: trailSVG, worldSVG: worldSVG, MOODS: MOODS
  });
})();
