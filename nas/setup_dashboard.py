import json
import os

# Le script génère les fichiers dans le dossier courant pour être universel
BASE_DIR = './'

# Version affichée dans le header : doit correspondre à la dernière version du changelog
VERSION = 'v0.4.0'

# ============================================================
# THÈMES
# ============================================================
THEMES = {
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
}

# ============================================================
# HTML
# ============================================================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PloufNAS</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #f5f5f5;
            --panel: #ffffff;
            --fg: #333333;
            --accent: #007bff;
            --temp-color: #FF3B3B;
            --hum-color: #3B8BFF;
        }
        * { box-sizing: border-box; }
        html, body { margin: 0; padding: 0; }
        body {
            background-color: var(--bg);
            color: var(--fg);
            font-family: Arial, sans-serif;
            padding: 12px;
            font-size: 13px;
            transition: all 0.3s ease;
            /* Pas de min-width : on laisse le CSS gérer */
        }

        /* Header */
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .header h1 { margin: 0; display: flex; align-items: baseline; gap: 8px; }
        .header h1 .title { font-size: 1.5em; }
        .header h1 .version { font-size: 0.8em; opacity: 0.5; font-weight: normal; }
        .header button {
            padding: 6px 14px; border-radius: 5px;
            border: 1px solid var(--fg); background: var(--panel); color: var(--fg);
            font-size: 0.9em; cursor: pointer; transition: all 0.2s;
        }
        .header button:hover { background: var(--accent); color: #fff; }

        /* ============================================= */
        /* BLOC AMBIANCE                                 */
        /* ============================================= */
        .ambiance {
            background-color: var(--panel); padding: 12px; border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex; flex-direction: column; align-items: center; gap: 10px;
            margin-bottom: 10px;
        }
        .ambiance .nas-icon { text-align: center; }
        .ambiance .nas-icon img { max-width: 70px; height: auto; }
        .ambiance .values { display: flex; gap: 20px; justify-content: center; align-items: center; }
        .ambiance .values .value {
            background: var(--accent); color: #fff;
            padding: 8px 14px; border-radius: 5px;
            font-weight: bold; font-size: 1.1em; white-space: nowrap;
        }
                        
        .ambiance .chart {
            position: relative;
            width: 100%;
            max-width: 100%;
            height: 180px;
            overflow: hidden;
        }
        .ambiance .chart canvas {
            width: 100% !important;
            height: 100% !important;
            display: block;
        }    

        /* ============================================= */
        /* MODE COMPLET : grille fixe 3 colonnes         */
        /* ============================================= */
        body.mode-full .ambiance {
            display: grid;
            grid-template-columns: 80px 140px 1fr;
            gap: 15px;
            align-items: center;
            padding: 10px 15px;
        }
        body.mode-full .ambiance .nas-icon { grid-column: 1; }
        body.mode-full .ambiance .nas-icon img { max-width: 80px; width: 100%; height: auto; }
        body.mode-full .ambiance .values {
            grid-column: 2;
            flex-direction: column;
            gap: 5px;
        }
        body.mode-full .ambiance .values .value { padding: 6px 10px; font-size: 1em; width: 100%; text-align: center; }
        body.mode-full .ambiance .chart { grid-column: 3; height: 130px; }

        /* ============================================= */
        /* BLOC DISQUES + CPU : grille fixe 2 colonnes   */
        /* ============================================= */
        .bottom-row {
            display: flex; flex-direction: column; gap: 10px;
        }
        .disks {
            background-color: var(--panel); padding: 10px; border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex; justify-content: space-around; flex-wrap: wrap; gap: 8px;
        }
        .disk { text-align: center; cursor: help; transition: transform 0.2s; }
        .disk:hover { transform: translateY(-3px); }
        .disk img { width: 45px; height: auto; }
        .disk .name { font-weight: bold; margin: 3px 0; color: var(--accent); font-size: 0.8em; }
        .disk .temp {
            background: var(--accent); color: #fff;
            padding: 2px 6px; border-radius: 3px; font-size: 0.75em;
            display: inline-block;
        }

        /* Bloc CPU + GPU */
        .system { display: flex; flex-direction: column; gap: 10px; }
        .system .block {
            background-color: var(--panel); padding: 10px; border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center;
        }
        .system .block img { width: 55px; height: auto; }
        .system .block .name { font-weight: bold; font-size: 0.95em; margin: 4px 0; color: var(--accent); }
        .system .block .temp {
            background: var(--accent); color: #fff;
            padding: 3px 10px; border-radius: 3px; display: inline-block; font-size: 0.85em;
        }
        .system .block.disabled { opacity: 0.4; }

        /* En mode COMPLET : disques à gauche + CPU à droite sur la même ligne */
        body.mode-full .bottom-row {
            display: grid;
            grid-template-columns: 1fr 200px;
            gap: 10px;
            align-items: stretch;
        }
        body.mode-full .disks { margin-bottom: 0; }
        body.mode-full .system { margin-bottom: 0; }

        /* ============================================= */
        /* MODALE PARAMÈTRES                             */
        /* ============================================= */
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0;
            width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000;
        }
        .modal-overlay.active { display: flex; justify-content: center; align-items: center; }
        .modal {
            background: var(--panel); color: var(--fg);
            border-radius: 10px; padding: 15px 20px;
            min-width: 420px; max-width: 90%; max-height: 95vh;
            overflow-y: auto;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            font-size: 0.9em;
        }
        .modal h2 {
            margin: 0 0 10px 0; display: flex; justify-content: space-between;
            align-items: center; font-size: 1.1em;
        }
        .modal h2 button { background: none; border: none; color: var(--fg); font-size: 1.3em; cursor: pointer; }
        .modal .section { margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--fg); }
        .modal .section:last-of-type { border-bottom: none; }
        .modal .section h3 { margin: 0 0 5px 0; font-size: 0.85em; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.5px; }
        .modal label { display: block; margin: 4px 0; font-size: 0.9em; }
        .modal select {
            width: 100%; padding: 4px 6px; margin-top: 2px;
            border-radius: 4px; border: 1px solid var(--fg);
            background: var(--bg); color: var(--fg); font-size: 0.9em;
        }
        .modal .checkbox { display: flex; align-items: center; gap: 8px; margin: 5px 0; font-size: 0.9em; }
        .modal .checkbox input { width: 15px; height: 15px; }
        .modal .checkbox.disabled { opacity: 0.4; pointer-events: none; }
        .modal .threshold { display: flex; align-items: center; gap: 8px; margin: 3px 0 6px 25px; font-size: 0.85em; }
        .modal .threshold select { width: auto; margin: 0; padding: 3px 5px; }
        .modal .color-row { display: flex; align-items: center; gap: 10px; margin: 6px 0; }
        .modal .color-row label { flex: 0 0 100px; margin: 0; }
        .modal .color-row input[type=color] {
            width: 40px; height: 25px; padding: 0; border: 1px solid var(--fg);
            border-radius: 4px; background: var(--bg); cursor: pointer;
        }
        .modal .color-row input[type=text] {
            width: 80px; padding: 3px 5px; border-radius: 4px;
            border: 1px solid var(--fg); background: var(--bg); color: var(--fg);
            font-size: 0.85em; font-family: monospace;
        }
        .modal .actions { text-align: right; margin-top: 10px; }
        .modal .actions button {
            padding: 6px 16px; border-radius: 5px; border: none;
            background: var(--accent); color: #fff; font-size: 0.9em; cursor: pointer;
        }

        /* ============================================= */
        /* RESPONSIVE (mobile)                           */
        /* ============================================= */
        @media (max-width: 600px) {
            body { min-width: auto; }
            body.mode-full .ambiance {
                grid-template-columns: 1fr;
                text-align: center;
            }
            body.mode-full .ambiance .nas-icon,
            body.mode-full .ambiance .values,
            body.mode-full .ambiance .chart { grid-column: 1; }
            body.mode-full .bottom-row { grid-template-columns: 1fr; }
            .modal { min-width: auto; width: 95%; font-size: 0.85em; }
        }
    </style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <h1>
            <span class="title">PloufNAS</span>
            <span class="version">""" + VERSION + """</span>
        </h1>
        <button onclick="openSettings()">⚙️ Paramètres</button>
    </div>

    <!-- Bloc ambiance -->
    <div class="ambiance">
        <div class="nas-icon">
            <img src="assets/NAS.png" alt="NAS" onerror="this.style.display='none'">
        </div>
        <div class="values">
            <div class="value" id="temp">-- °C</div>
            <div class="value" id="hum">-- %</div>
        </div>
        <div class="chart">
            <canvas id="myChart"></canvas>
        </div>
    </div>

    <!-- Rangée du bas : disques + CPU/GPU -->
    <div class="bottom-row" id="bottomRow">
        <div class="disks" id="disksBlock"></div>
        <div class="system" id="systemBlock">
            <div class="block" id="cpuBlock">
                <img src="assets/CPU.png" alt="CPU" onerror="this.style.display='none'">
                <div class="name">CPU</div>
                <div class="temp" id="cpuTemp">-- °C</div>
            </div>
            <div class="block" id="gpuBlock">
                <img src="assets/GPU.png" alt="GPU" onerror="this.style.display='none'">
                <div class="name">GPU</div>
                <div class="temp" id="gpuTemp">-- °C</div>
            </div>
        </div>
    </div>

    <!-- Modale Paramètres -->
    <div class="modal-overlay" id="settingsModal">
        <div class="modal">
            <h2>
                ⚙️ Paramètres
                <button onclick="closeSettings()">×</button>
            </h2>

            <!-- 1. Mode d'affichage -->
            <div class="section">
                <h3>Mode d'affichage</h3>
                <label>Mode :
                    <select id="modeSelector">
                        <option value="basic">Basique</option>
                        <option value="full">Complet</option>
                    </select>
                </label>
            </div>

            <!-- 2. Composants -->
            <div class="section" id="fullModeOptions">
                <h3>Composants à afficher (mode complet)</h3>
                <div class="checkbox">
                    <input type="checkbox" id="showDisks" checked>
                    <label for="showDisks">Afficher les disques durs</label>
                </div>
                <div class="checkbox">
                    <input type="checkbox" id="showCpu" checked>
                    <label for="showCpu">Afficher le CPU</label>
                </div>
                <div class="checkbox disabled" id="showGpuContainer">
                    <input type="checkbox" id="showGpu" disabled>
                    <label for="showGpu">Afficher le GPU (non détecté)</label>
                </div>
            </div>

            <!-- 3. Couleurs -->
            <div class="section">
                <h3>Couleurs du graphique</h3>
                <div class="color-row">
                    <label for="tempColor">Température :</label>
                    <input type="color" id="tempColor" value="#FF3B3B">
                    <input type="text" id="tempColorText" value="#FF3B3B" maxlength="7">
                </div>
                <div class="color-row">
                    <label for="humColor">Humidité :</label>
                    <input type="color" id="humColor" value="#3B8BFF">
                    <input type="text" id="humColorText" value="#3B8BFF" maxlength="7">
                </div>
            </div>

            <!-- 4. Alertes -->
            <div class="section">
                <h3>Alertes système</h3>
                <div class="checkbox">
                    <input type="checkbox" id="alertCpu" checked>
                    <label for="alertCpu">Alerte température CPU</label>
                </div>
                <div class="threshold">
                    <label>Seuil :</label>
                    <select id="alertCpuThreshold">
                        <option value="60">60 °C</option>
                        <option value="65">65 °C</option>
                        <option value="70">70 °C</option>
                        <option value="75" selected>75 °C</option>
                        <option value="80">80 °C</option>
                        <option value="85">85 °C</option>
                    </select>
                </div>

                <div class="checkbox">
                    <input type="checkbox" id="alertDisks" checked>
                    <label for="alertDisks">Alerte température disques</label>
                </div>
                <div class="threshold">
                    <label>Seuil :</label>
                    <select id="alertDisksThreshold">
                        <option value="40">40 °C</option>
                        <option value="45">45 °C</option>
                        <option value="50" selected>50 °C</option>
                        <option value="55">55 °C</option>
                        <option value="60">60 °C</option>
                    </select>
                </div>

                <div class="checkbox">
                    <input type="checkbox" id="alertSmart" checked>
                    <label for="alertSmart">Alerte état SMART dégradé</label>
                </div>

                <div class="checkbox disabled" id="alertGpuContainer">
                    <input type="checkbox" id="alertGpu" disabled>
                    <label for="alertGpu">Alerte température GPU (non détecté)</label>
                </div>
                <div class="threshold">
                    <label>Seuil :</label>
                    <select id="alertGpuThreshold">
                        <option value="70">70 °C</option>
                        <option value="75">75 °C</option>
                        <option value="80" selected>80 °C</option>
                        <option value="85">85 °C</option>
                        <option value="90">90 °C</option>
                    </select>
                </div>
            </div>

            <!-- 5. Thème (en bas) -->
            <div class="section">
                <h3>Thème</h3>
                <label>Thème :
                    <select id="themeSelector"></select>
                </label>
                <div class="checkbox">
                    <input type="checkbox" id="keepTheme">
                    <label for="keepTheme">Garder le thème au rechargement</label>
                </div>
            </div>

            <div class="actions">
                <button onclick="applySettings()">Appliquer</button>
            </div>
        </div>
    </div>

    <script>
        const THEMES = """ + json.dumps(THEMES) + """;
        const HUMIDITY_THRESHOLD = 80;

        let chart;
        let tempColor = '#FF3B3B';
        let humColor  = '#3B8BFF';

        // ============================================================
        // COULEURS
        // ============================================================
        function applyColors() {
            document.documentElement.style.setProperty('--temp-color', tempColor);
            document.documentElement.style.setProperty('--hum-color', humColor);
            if (chart) {
                chart.data.datasets[0].borderColor = tempColor;
                chart.data.datasets[1].borderColor = humColor;
                chart.update();
            }
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
            if (chart) chart.update();
        }

        function initThemes() {
            const selector = document.getElementById('themeSelector');
            const keys = Object.keys(THEMES);
            keys.forEach(k => {
                let opt = document.createElement('option');
                opt.value = k;
                opt.innerText = k;
                selector.appendChild(opt);
            });
            const randomTheme = keys[Math.floor(Math.random() * keys.length)];
            selector.value = randomTheme;
            applyTheme(randomTheme);
            selector.addEventListener('change', (e) => applyTheme(e.target.value));
            document.getElementById('modeSelector').addEventListener('change', updateModeUI);
        }

        // ============================================================
        // COLOR PICKERS
        // ============================================================
        function initColorPickers() {
            const tColor    = document.getElementById('tempColor');
            const tColorTxt = document.getElementById('tempColorText');
            const hColor    = document.getElementById('humColor');
            const hColorTxt = document.getElementById('humColorText');

            tColor.addEventListener('input', (e) => {
                tColorTxt.value = e.target.value.toUpperCase();
                tempColor = e.target.value;
                applyColors();
            });
            hColor.addEventListener('input', (e) => {
                hColorTxt.value = e.target.value.toUpperCase();
                humColor = e.target.value;
                applyColors();
            });

            tColorTxt.addEventListener('change', (e) => {
                const val = e.target.value;
                if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
                    tColor.value = val;
                    tempColor = val;
                    applyColors();
                }
            });
            hColorTxt.addEventListener('change', (e) => {
                const val = e.target.value;
                if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
                    hColor.value = val;
                    humColor = val;
                    applyColors();
                }
            });
        }

        // ============================================================
        // MODALE
        // ============================================================
        function openSettings() {
            document.getElementById('settingsModal').classList.add('active');
            updateModeUI();
        }
        function closeSettings() {
            document.getElementById('settingsModal').classList.remove('active');
        }
        function applySettings() {
            updateModeUI();
            tempColor = document.getElementById('tempColor').value;
            humColor  = document.getElementById('humColor').value;
            applyColors();
            saveAlertes();
            closeSettings();
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
        // SAUVEGARDE / CHARGEMENT alertes.json
        // ============================================================
        async function saveAlertes() {
            const payload = {
                cpu: {
                    enabled: document.getElementById('alertCpu').checked,
                    threshold: parseInt(document.getElementById('alertCpuThreshold').value)
                },
                disks: {
                    enabled: document.getElementById('alertDisks').checked,
                    threshold: parseInt(document.getElementById('alertDisksThreshold').value)
                },
                smart: { enabled: document.getElementById('alertSmart').checked },
                gpu: {
                    enabled: document.getElementById('alertGpu').checked,
                    threshold: parseInt(document.getElementById('alertGpuThreshold').value)
                },
                colors: {
                    temperature: tempColor,
                    humidity: humColor
                }
            };
            try {
                await fetch('/api/alertes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (e) { console.error('Erreur sauvegarde:', e); }
        }

        async function loadAlertes() {
            try {
                const res = await fetch('/api/alertes');
                const data = await res.json();
                if (data.cpu)   {
                    document.getElementById('alertCpu').checked = data.cpu.enabled;
                    document.getElementById('alertCpuThreshold').value = data.cpu.threshold;
                }
                if (data.disks) {
                    document.getElementById('alertDisks').checked = data.disks.enabled;
                    document.getElementById('alertDisksThreshold').value = data.disks.threshold;
                }
                if (data.smart) document.getElementById('alertSmart').checked = data.smart.enabled;
                if (data.gpu)   {
                    document.getElementById('alertGpu').checked = data.gpu.enabled;
                    document.getElementById('alertGpuThreshold').value = data.gpu.threshold;
                }
                if (data.colors) {
                    tempColor = data.colors.temperature || tempColor;
                    humColor  = data.colors.humidity    || humColor;
                    document.getElementById('tempColor').value = tempColor;
                    document.getElementById('tempColorText').value = tempColor.toUpperCase();
                    document.getElementById('humColor').value = humColor;
                    document.getElementById('humColorText').value = humColor.toUpperCase();
                }
                applyColors();
            } catch (e) { console.error('Erreur chargement:', e); }
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
                const tooltip = `Modèle : ${d.model}\\nN° série : ${d.serial}\\nCapacité : ${d.capacity}\\nÉtat SMART : ${d.smart}\\nTempérature : ${d.temp} °C\\nEmplacement : ${d.dev}`;
                const div = document.createElement('div');
                div.className = 'disk';
                div.title = tooltip;
                div.innerHTML = `
                    <img src="assets/DD.png" alt="${d.name}" onerror="this.style.display='none'">
                    <div class="name">${d.name}</div>
                    <div class="temp">${d.temp} °C</div>
                `;
                container.appendChild(div);
            });
        }

        function renderSystem() {
            document.getElementById('cpuTemp').innerText = '45 °C';
            const cpuTooltip = `Modèle : Intel Core i5-8500\\nCœurs : 6\\nFréquence : 3.0 GHz\\nTempérature : 45 °C\\nCharge : 12 %`;
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
                                legend: { labels: { color: 'var(--fg)', boxWidth: 15, font: { size: 11 } } }
                            },
                            scales: {
                                y:  { type: 'linear', display: true, position: 'left',  min: 15, max: 35,
                                      title: { display: true, text: 'Temp (°C)', color: 'var(--fg)', font: { size: 10 } },
                                      ticks: { color: 'var(--fg)', font: { size: 10 } } },
                                y1: { type: 'linear', display: true, position: 'right', min: 20, max: 80,
                                      title: { display: true, text: 'Hum (%)', color: 'var(--fg)', font: { size: 10 } },
                                      grid: { drawOnChartArea: false },
                                      ticks: { color: 'var(--fg)', font: { size: 10 } } },
                                x:  { ticks: { color: 'var(--fg)', maxRotation: 45, font: { size: 9 } } }
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

        initThemes();
        initColorPickers();
        renderDisks();
        renderSystem();
        updateModeUI();
        loadAlertes();
        updateData();
        setInterval(updateData, 5000);

        // Forcer un resize après le premier rendu (laisse le temps au layout de se stabiliser)
        setTimeout(() => { if (chart) chart.resize(); }, 500);
    </script>
</body>
</html>"""

# ============================================================
# FLASK
# ============================================================
PYTHON_CONTENT = """from flask import Flask, jsonify, send_file, request
import csv
import os
import json

app = Flask(__name__, static_folder='assets', static_url_path='/assets')
CSV_FILE = './climat.csv'
ALERTES_FILE = './alertes.json'

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api')
def api():
    data = []
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append({
                    'time': row['Date et Heure'],
                    'temp': row['Temperature_C'],
                    'hum': row['Humidite_Pct']
                })
    except Exception as e:
        print('Error:', e)
    return jsonify(data[-30:])

@app.route('/api/alertes', methods=['GET'])
def get_alertes():
    try:
        with open(ALERTES_FILE, 'r') as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({})

@app.route('/api/alertes', methods=['POST'])
def save_alertes():
    try:
        data = request.get_json()
        with open(ALERTES_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
"""

# ============================================================
# ÉCRITURE
# ============================================================
with open(BASE_DIR + 'index.html', 'w', encoding='utf-8') as f:
    f.write(HTML_CONTENT)
with open(BASE_DIR + 'dashboard.py', 'w', encoding='utf-8') as f:
    f.write(PYTHON_CONTENT)
print("✅ Dashboard et thèmes générés avec succès dans le dossier courant !")