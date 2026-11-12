// PloufNAS — dashboard (chargé par static/index.html)

const THEMES = {
    "[Sombre] Midnight Garage": {"BG": "#151515", "PANEL": "#1F1F1F", "FG": "#EAEAEA", "ACCENT": "#FF9800"},
    "[Sombre] AIR-KLM Night flight": {"BG": "#0B1E2D", "PANEL": "#102A3D", "FG": "#EAF6FF", "ACCENT": "#00A1DE"},
    "[Sombre] Café Serré": {"BG": "#1B120C", "PANEL": "#2A1C14", "FG": "#F2E6D8", "ACCENT": "#C28E5C"},
    "[Sombre] Matrix Déjà Vu": {"BG": "#000A00", "PANEL": "#001F00", "FG": "#00FF66", "ACCENT": "#00FF00"},
    "[Sombre] Miami Vice 1987": {"BG": "#14002E", "PANEL": "#2B0057", "FG": "#FFF0FF", "ACCENT": "#00FFD5"},
    "[Sombre] Cyber Licorne": {"BG": "#1A0026", "PANEL": "#2E004F", "FG": "#F6E7FF", "ACCENT": "#FF2CF7"},
    "[Clair] AIR-KLM Day flight": {"BG": "#EAF6FF", "PANEL": "#D6EEF9", "FG": "#0B2A3F", "ACCENT": "#00A1DE"},
    "[Clair] Matin Brumeux": {"BG": "#E6E7E8", "PANEL": "#D4D7DB", "FG": "#1E1F22", "ACCENT": "#6B7C93"},
    "[Clair] Latte Vanille": {"BG": "#FAF6F1", "PANEL": "#EFE6DC", "FG": "#3D2E22", "ACCENT": "#D8B892"},
    "[Clair] Miellerie La Divette": {"BG": "#E6B65C", "PANEL": "#F5E6CC", "FG": "#50371A", "ACCENT": "#F2B705"},
    "[Pouêt] Chewing-gum Océan": {"BG": "#00A6C8", "PANEL": "#0083A1", "FG": "#082026", "ACCENT": "#FF4FD8"},
    "[Pouêt] Pamplemousse": {"BG": "#FF4A1C", "PANEL": "#E63B10", "FG": "#1A0B00", "ACCENT": "#00E5FF"},
    "[Pouêt] Raisin Toxique": {"BG": "#7A00FF", "PANEL": "#5B00C9", "FG": "#0F001A", "ACCENT": "#39FF14"},
    "[Pouêt] Citron qui pique": {"BG": "#FFF200", "PANEL": "#E6D800", "FG": "#1A1A00", "ACCENT": "#0066FF"},
    "[Pouêt] Barbie Apocalypse": {"BG": "#FF1493", "PANEL": "#004D40", "FG": "#E8FFF8", "ACCENT": "#FFEB3B"},
    "[Pouêt] Compagnie Créole": {"BG": "#8B3A1A", "PANEL": "#F2C94C", "FG": "#5A2E0C", "ACCENT": "#8B3A1A"}
};

let chart;
let tempColor = '#FF3B3B';
let humColor  = '#3B8BFF';
let motDePasse = null;          // gardé en mémoire le temps de la page uniquement
let seuils = { temp_max: 30, hum_max: 80 };

// ============================================================
// PRÉFÉRENCES D'AFFICHAGE (propres à ce navigateur)
// ============================================================
const CLE_PREFS = 'ploufnas.prefs';

function lirePrefs() {
    try {
        return JSON.parse(localStorage.getItem(CLE_PREFS)) || {};
    } catch (e) {
        return {};
    }
}

function enregistrerPrefs() {
    const prefs = {
        mode: document.getElementById('modeSelector').value,
        showDisks: document.getElementById('showDisks').checked,
        showCpu: document.getElementById('showCpu').checked,
        keepTheme: document.getElementById('keepTheme').checked,
        theme: document.getElementById('themeSelector').value
    };
    try {
        localStorage.setItem(CLE_PREFS, JSON.stringify(prefs));
    } catch (e) { /* navigation privée : préférences non conservées */ }
}

function appliquerPrefs() {
    const prefs = lirePrefs();
    if (prefs.mode) document.getElementById('modeSelector').value = prefs.mode;
    if (typeof prefs.showDisks === 'boolean') document.getElementById('showDisks').checked = prefs.showDisks;
    if (typeof prefs.showCpu === 'boolean') document.getElementById('showCpu').checked = prefs.showCpu;
    document.getElementById('keepTheme').checked = !!prefs.keepTheme;
    return prefs;
}

// ============================================================
// COULEURS
// ============================================================
function couleurTexte() {
    // Chart.js dessine sur un canvas : il ne comprend pas var(--fg).
    return getComputedStyle(document.documentElement).getPropertyValue('--fg').trim() || '#333';
}

function appliquerCouleursGraphique() {
    if (!chart) return;
    const fg = couleurTexte();
    chart.data.datasets[0].borderColor = tempColor;
    chart.data.datasets[1].borderColor = humColor;
    chart.options.plugins.legend.labels.color = fg;
    for (const axe of Object.values(chart.options.scales)) {
        axe.ticks.color = fg;
        if (axe.title) axe.title.color = fg;
    }
    chart.update();
}

function applyColors() {
    document.documentElement.style.setProperty('--temp-color', tempColor);
    document.documentElement.style.setProperty('--hum-color', humColor);
    appliquerCouleursGraphique();
}

// ============================================================
// THÈME
// ============================================================
function applyTheme(themeName) {
    const t = THEMES[themeName];
    if (!t) return;
    document.documentElement.style.setProperty('--bg', t.BG);
    document.documentElement.style.setProperty('--panel', t.PANEL);
    document.documentElement.style.setProperty('--fg', t.FG);
    document.documentElement.style.setProperty('--accent', t.ACCENT);
    appliquerCouleursGraphique();
}

function initThemes(prefs) {
    const selector = document.getElementById('themeSelector');
    const keys = Object.keys(THEMES);
    keys.forEach(k => {
        const opt = document.createElement('option');
        opt.value = k;
        opt.innerText = k;
        selector.appendChild(opt);
    });
    const theme = (prefs.keepTheme && THEMES[prefs.theme])
        ? prefs.theme
        : keys[Math.floor(Math.random() * keys.length)];
    selector.value = theme;
    applyTheme(theme);
    selector.addEventListener('change', (e) => applyTheme(e.target.value));
    document.getElementById('modeSelector').addEventListener('change', updateModeUI);
}

// ============================================================
// COLOR PICKERS
// ============================================================
function initColorPickers() {
    const paires = [
        ['tempColor', 'tempColorText', v => { tempColor = v; }],
        ['humColor', 'humColorText', v => { humColor = v; }]
    ];
    for (const [idPicker, idTexte, affecter] of paires) {
        const picker = document.getElementById(idPicker);
        const texte = document.getElementById(idTexte);
        picker.addEventListener('input', (e) => {
            texte.value = e.target.value.toUpperCase();
            affecter(e.target.value);
            applyColors();
        });
        texte.addEventListener('change', (e) => {
            const val = e.target.value;
            if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
                picker.value = val;
                affecter(val);
                applyColors();
            }
        });
    }
}

// ============================================================
// MODALE
// ============================================================
function afficherMessage(texte, type) {
    const zone = document.getElementById('settingsMessage');
    zone.textContent = texte || '';
    zone.className = 'message' + (type ? ' ' + type : '');
}

function openSettings() {
    afficherMessage('');
    document.getElementById('settingsModal').classList.add('active');
    updateModeUI();
}

function closeSettings() {
    document.getElementById('settingsModal').classList.remove('active');
}

async function applySettings() {
    // Affichage : appliqué tout de suite, dans ce navigateur uniquement.
    updateModeUI();
    tempColor = document.getElementById('tempColor').value;
    humColor  = document.getElementById('humColor').value;
    applyColors();
    enregistrerPrefs();

    // Réglages partagés (seuils, alertes, couleurs) : enregistrés sur le NAS.
    const champ = document.getElementById('settingsPassword');
    if (champ.value) motDePasse = champ.value;
    if (!motDePasse) {
        afficherMessage('Affichage appliqué. Saisissez le mot de passe pour enregistrer les seuils et les alertes sur le NAS.', 'info');
        return;
    }
    const resultat = await saveConfig();
    if (resultat.ok) {
        champ.value = '';
        closeSettings();
    } else {
        if (resultat.code === 401) motDePasse = null;
        afficherMessage(resultat.message, 'erreur');
    }
}

function updateModeUI() {
    const mode = document.getElementById('modeSelector').value;
    const fullOptions = document.getElementById('fullModeOptions');

    if (mode === 'basic') {
        document.body.classList.remove('mode-full');
        fullOptions.querySelectorAll('input').forEach(i => i.disabled = true);
        fullOptions.querySelectorAll('.checkbox').forEach(c => c.classList.add('disabled'));
        document.getElementById('bottomRow').style.display = 'none';
    } else {
        document.body.classList.add('mode-full');
        fullOptions.querySelectorAll('input').forEach(i => {
            if (i.id !== 'showGpu') i.disabled = false;
        });
        fullOptions.querySelectorAll('.checkbox').forEach(c => {
            if (c.id !== 'showGpuContainer') c.classList.remove('disabled');
        });
        document.getElementById('bottomRow').style.display = 'grid';

        // Disques
        document.getElementById('disksBlock').style.display =
            document.getElementById('showDisks').checked ? 'flex' : 'none';

        // CPU
        document.getElementById('cpuBlock').style.display =
            document.getElementById('showCpu').checked ? 'block' : 'none';

        // GPU (uniquement si coché)
        document.getElementById('gpuBlock').style.display =
            document.getElementById('showGpu').checked ? 'block' : 'none';
    }
}

// ============================================================
// CONFIG PARTAGÉE (config.json sur le NAS)
// ============================================================
function lireReglagesFormulaire() {
    const nombre = id => parseFloat(document.getElementById(id).value);
    const entier = id => parseInt(document.getElementById(id).value, 10);
    const coche = id => document.getElementById(id).checked;
    return {
        seuils: {
            temp_max: nombre('seuilTemp'),
            hum_max: nombre('seuilHum')
        },
        alertes_systeme: {
            cpu:   { enabled: coche('alertCpu'),   threshold: entier('alertCpuThreshold') },
            disks: { enabled: coche('alertDisks'), threshold: entier('alertDisksThreshold') },
            smart: { enabled: coche('alertSmart') },
            gpu:   { enabled: coche('alertGpu'),   threshold: entier('alertGpuThreshold') }
        },
        couleurs: { temperature: tempColor, humidity: humColor }
    };
}

function remplirFormulaire(data) {
    if (data.seuils) {
        seuils = data.seuils;
        document.getElementById('seuilTemp').value = data.seuils.temp_max;
        document.getElementById('seuilHum').value = data.seuils.hum_max;
    }
    const a = data.alertes_systeme || {};
    if (a.cpu) {
        document.getElementById('alertCpu').checked = a.cpu.enabled;
        document.getElementById('alertCpuThreshold').value = a.cpu.threshold;
    }
    if (a.disks) {
        document.getElementById('alertDisks').checked = a.disks.enabled;
        document.getElementById('alertDisksThreshold').value = a.disks.threshold;
    }
    if (a.smart) document.getElementById('alertSmart').checked = a.smart.enabled;
    if (a.gpu) {
        document.getElementById('alertGpu').checked = a.gpu.enabled;
        document.getElementById('alertGpuThreshold').value = a.gpu.threshold;
    }
    if (data.couleurs) {
        tempColor = data.couleurs.temperature || tempColor;
        humColor  = data.couleurs.humidity    || humColor;
        document.getElementById('tempColor').value = tempColor;
        document.getElementById('tempColorText').value = tempColor.toUpperCase();
        document.getElementById('humColor').value = humColor;
        document.getElementById('humColorText').value = humColor.toUpperCase();
    }
    if (typeof data.mot_de_passe_defini === 'boolean') {
        document.getElementById('passwordHint').textContent = data.mot_de_passe_defini
            ? 'Nécessaire pour enregistrer les seuils, les alertes et les couleurs sur le NAS.'
            : 'Aucun mot de passe défini sur le NAS : lancez « sudo python3 config.py --mot-de-passe ».';
    }
    applyColors();
}

async function saveConfig() {
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + btoa(unescape(encodeURIComponent(':' + motDePasse)))
            },
            body: JSON.stringify(lireReglagesFormulaire())
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            return { ok: false, code: res.status, message: data.message || ('Erreur ' + res.status) };
        }
        remplirFormulaire(data);
        return { ok: true };
    } catch (e) {
        return { ok: false, code: 0, message: 'Le NAS est injoignable.' };
    }
}

async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        if (!res.ok) {
            console.error('Erreur chargement :', data.message);
            return;
        }
        if (data.version) document.getElementById('version').textContent = 'v' + data.version;
        remplirFormulaire(data);
    } catch (e) { console.error('Erreur chargement :', e); }
}

// ============================================================
// DONNÉES DÉMO
// ============================================================
function renderDisks() {
    const disks = [
        { name: 'SSD système', model: 'Samsung SSD 870 EVO 500GB', serial: 'S5Y2NG0R123456', capacity: '500 Go', smart: '✅ Sain', temp: 32, dev: '/dev/sda' },
        { name: 'DD#1', model: 'WDC WD30EFRX-68EUZN0', serial: 'WD-WCC4N12345678', capacity: '3 To', smart: '✅ Sain', temp: 35, dev: '/dev/sdb' },
        { name: 'DD#2', model: 'WDC WD30EFRX-68EUZN0', serial: 'WD-WCC4N23456789', capacity: '3 To', smart: '✅ Sain', temp: 36, dev: '/dev/sdc' },
        { name: 'DD#3', model: 'WDC WD30EFRX-68EUZN0', serial: 'WD-WCC4N34567890', capacity: '3 To', smart: '✅ Sain', temp: 34, dev: '/dev/sdd' },
        { name: 'DD#4', model: 'WDC WD30EFRX-68EUZN0', serial: 'WD-WCC4N45678901', capacity: '3 To', smart: '✅ Sain', temp: 37, dev: '/dev/sde' },
        { name: 'DD#5', model: 'WDC WD30EFRX-68EUZN0', serial: 'WD-WCC4N56789012', capacity: '3 To', smart: '✅ Sain', temp: 35, dev: '/dev/sdf' }
    ];
    const container = document.getElementById('disksBlock');
    container.innerHTML = '';
    disks.forEach(d => {
        const tooltip = `Modèle : ${d.model}\nN° série : ${d.serial}\nCapacité : ${d.capacity}\nÉtat SMART : ${d.smart}\nTempérature : ${d.temp} °C\nEmplacement : ${d.dev}`;
        const div = document.createElement('div');
        div.className = 'disk';
        div.title = tooltip;
        div.innerHTML = `
            <img src="static/img/DD.png" alt="${d.name}" onerror="this.style.display='none'">
            <div class="name">${d.name}</div>
            <div class="temp">${d.temp} °C</div>
        `;
        container.appendChild(div);
    });
}

function renderSystem() {
    document.getElementById('cpuTemp').innerText = '45 °C';
    const cpuTooltip = `Modèle : Intel Core i5-8500\nCœurs : 6\nFréquence : 3.0 GHz\nTempérature : 45 °C\nCharge : 12 %`;
    document.getElementById('cpuBlock').title = cpuTooltip;

    document.getElementById('gpuTemp').innerText = '-- °C';
    document.getElementById('gpuBlock').classList.add('disabled');
    document.getElementById('gpuBlock').title = 'Aucun GPU compatible détecté';
}

// ============================================================
// GRAPHIQUE
// ============================================================
async function updateData() {
    let res = await fetch('/api');
    let data = await res.json();
    if (data.length > 0) {
        let last = data[data.length - 1];
        document.getElementById('temp').innerText = last.temp + ' °C';
        document.getElementById('hum').innerText = last.hum + ' %';

        let labels = data.map(d => d.time.split(' ')[1]);
        let temps = data.map(d => parseFloat(d.temp));
        let hums = data.map(d => parseFloat(d.hum));

        if (chart) {
            chart.data.labels = labels;
            chart.data.datasets[0].data = temps;
            chart.data.datasets[1].data = hums;
            chart.update();
        } else {
            const fg = couleurTexte();
            let ctx = document.getElementById('myChart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Température (°C)', data: temps, borderColor: tempColor, backgroundColor: 'rgba(0,0,0,0)', yAxisID: 'y',  tension: 0.3, pointRadius: 2 },
                        { label: 'Humidité (%)',     data: hums,  borderColor: humColor,  backgroundColor: 'rgba(0,0,0,0)', yAxisID: 'y1', tension: 0.3, pointRadius: 2 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { labels: { color: fg, boxWidth: 15, font: { size: 11 } } }
                    },
                    scales: {
                        y:  { type: 'linear', display: true, position: 'left',  suggestedMin: 15, suggestedMax: 35,
                              title: { display: true, text: 'Temp (°C)', color: fg, font: { size: 10 } },
                              ticks: { color: fg, font: { size: 10 } } },
                        y1: { type: 'linear', display: true, position: 'right', suggestedMin: 20, suggestedMax: 80,
                              title: { display: true, text: 'Hum (%)', color: fg, font: { size: 10 } },
                              grid: { drawOnChartArea: false },
                              ticks: { color: fg, font: { size: 10 } } },
                        x:  { ticks: { color: fg, maxRotation: 45, font: { size: 9 } } }
                    }
                }
            });
        }
    }
}

// ============================================================
// INIT
// ============================================================

// Forcer Chart.js à se redimensionner quand le conteneur change
const chartContainer = document.querySelector('.ambiance .chart');
if (window.ResizeObserver && chartContainer) {
    const ro = new ResizeObserver(() => {
        if (chart) chart.resize();
    });
    ro.observe(chartContainer);
}

const prefs = appliquerPrefs();
initThemes(prefs);
initColorPickers();
renderDisks();
renderSystem();
updateModeUI();
loadConfig();
updateData();
setInterval(updateData, 5000);

// Forcer un resize après le premier rendu (laisse le temps au layout de se stabiliser)
setTimeout(() => { if (chart) chart.resize(); }, 500);

