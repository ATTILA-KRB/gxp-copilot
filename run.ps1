# ============================================================
# GxP Copilot - demarrage complet (Windows / PowerShell 5.1+)
#
# Usage :
#   .\run.ps1                  # tout : base, ingestion, API, UI
#   .\run.ps1 -SkipIngestion   # sans re-ingestion (deja indexe)
#   .\run.ps1 -ApiOnly         # base + API, sans l'UI
#
# La fenetre ne se ferme JAMAIS seule : chaque erreur est expliquee,
# journalisee dans run.log, et attend une touche avant de quitter.
# ============================================================

param(
    [switch]$SkipIngestion,
    [switch]$ApiOnly
)

# "Continue" et non "Stop" : avec Stop, la moindre ligne stderr d'un outil
# natif (docker, ollama...) devient une exception fatale et ferme la fenetre.
$ErrorActionPreference = "Continue"

$Root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$LogFile = Join-Path $Root "run.log"
"=== run.ps1 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $LogFile -Encoding utf8

function Log($message) {
    $message | Out-File $LogFile -Append -Encoding utf8
}

function Step($message) {
    Write-Host "`n=== $message ===" -ForegroundColor Cyan
    Log "STEP: $message"
}

function Done($message) {
    Write-Host "[OK] $message" -ForegroundColor Green
    Log "OK: $message"
}

function Warn($message) {
    Write-Host "[ATTENTION] $message" -ForegroundColor Yellow
    Log "WARN: $message"
}

function Fail($message, $hint = $null) {
    Write-Host ""
    Write-Host "[ERREUR] $message" -ForegroundColor Red
    if ($hint) { Write-Host "[PISTE]  $hint" -ForegroundColor Yellow }
    Log "FAIL: $message"
    Write-Host ""
    Write-Host "Journal complet : $LogFile" -ForegroundColor DarkGray
    Read-Host "Appuyez sur Entree pour fermer"
    exit 1
}

# Execute un outil natif, capture stdout+stderr dans le log, renvoie la sortie.
function Run($exe, [string[]]$arguments) {
    Log "RUN: $exe $($arguments -join ' ')"
    $output = & $exe @arguments 2>&1 | Out-String
    Log $output
    return $output
}

try {
    Set-Location $Root

    # ---------- 0. PATH a jour ----------
    # Recharge le PATH depuis le registre : un outil installe apres l'ouverture
    # du terminal (uv, ollama...) est ainsi trouve sans redemarrer la session.
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $localBin = Join-Path $env:USERPROFILE ".local\bin"
    $env:Path = "$machinePath;$userPath;$localBin"

    # ---------- 1. Prerequis ----------
    Step "Verification des prerequis"
    $hints = @{
        docker = "Installer Docker Desktop : https://www.docker.com/products/docker-desktop/"
        uv     = "Installer uv : https://docs.astral.sh/uv/getting-started/installation/"
        npm    = "Installer Node.js (inclut npm) : https://nodejs.org"
        ollama = "Installer Ollama : https://ollama.com/download"
    }
    foreach ($tool in @("docker", "uv", "npm", "ollama")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Fail "'$tool' introuvable dans le PATH." $hints[$tool]
        }
    }
    Done "docker / uv / npm / ollama presents"

    # Docker Desktop demarre ?
    $null = Run "docker" @("info")
    if ($LASTEXITCODE -ne 0) {
        Fail "Le moteur Docker ne repond pas." "Lancer Docker Desktop, attendre l'icone verte, puis relancer ce script."
    }
    Done "Moteur Docker actif"

    # ---------- 2. Configuration (.env) ----------
    Step "Configuration (.env)"
    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path $envPath)) {
        Copy-Item (Join-Path $Root ".env.example") $envPath
        Fail ".env absent - cree depuis .env.example a l'instant." "Editer .env (MISTRAL_API_KEY, COHERE_API_KEY, POSTGRES_PASSWORD) puis relancer."
    }
    $envContent = Get-Content $envPath -Raw
    foreach ($key in @("MISTRAL_API_KEY", "COHERE_API_KEY")) {
        if ($envContent -match "(?m)^$key=\s*$") {
            Warn "$key est vide dans .env - les requetes en mode cloud echoueront."
        }
    }
    Done ".env present"

    # ---------- 3. Base de donnees ----------
    Step "Base de donnees (Postgres + pgvector)"
    $null = Run "docker" @("compose", "up", "-d")
    if ($LASTEXITCODE -ne 0) {
        Fail "docker compose up a echoue." "Voir run.log ; verifier docker-compose.yml et que le port 5432 est libre."
    }
    Write-Host "Attente de PostgreSQL " -NoNewline
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        $health = (& docker inspect --format "{{.State.Health.Status}}" gxp-db 2>&1 | Out-String).Trim()
        if ($health -eq "healthy") { $ready = $true; break }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
    Write-Host ""
    if (-not $ready) {
        Fail "PostgreSQL n'est pas passe 'healthy' en 60 s." "Diagnostiquer avec : docker compose logs db"
    }
    Done "PostgreSQL pret"

    # ---------- 4. Embeddings (Ollama + bge-m3) ----------
    Step "Modele d'embedding (bge-m3 via Ollama)"
    $models = Run "ollama" @("list")
    if ($LASTEXITCODE -ne 0) {
        Fail "Ollama ne repond pas." "Demarrer l'application Ollama (icone dans la barre des taches) puis relancer."
    }
    if ($models -notmatch "bge-m3") {
        Write-Host "Telechargement de bge-m3 (~1,2 Go, une seule fois)..."
        & ollama pull bge-m3
        if ($LASTEXITCODE -ne 0) {
            Fail "ollama pull bge-m3 a echoue." "Verifier la connexion reseau puis relancer."
        }
    }
    Done "bge-m3 disponible"

    # ---------- 5. Dependances Python ----------
    Step "Dependances Python (uv sync)"
    $null = Run "uv" @("sync")
    if ($LASTEXITCODE -ne 0) {
        Fail "uv sync a echoue." "Voir run.log (version de Python >= 3.11 requise)."
    }
    Done "Environnement Python pret"

    # ---------- 6. Ingestion du corpus (idempotente) ----------
    if (-not $SkipIngestion) {
        Step "Ingestion du corpus public (idempotente)"
        & uv run python -m ingestion.download
        if ($LASTEXITCODE -ne 0) {
            Fail "Telechargement du corpus incomplet." "Relancer (reprise idempotente) ; voir les [FAIL] ci-dessus."
        }
        & uv run python -m ingestion.index
        if ($LASTEXITCODE -ne 0) {
            Fail "Indexation echouee." "Verifier qu'Ollama tourne (embeddings) et que Postgres est sain ; voir ci-dessus."
        }
        Done "Corpus indexe"
    } else {
        Warn "Ingestion sautee (-SkipIngestion)."
    }

    # ---------- 7. API FastAPI ----------
    Step "API FastAPI -> http://localhost:8001"
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
        "Set-Location '$Root'; Write-Host 'API GxP Copilot (Ctrl+C pour arreter)' -ForegroundColor Cyan; uv run uvicorn app.main:app --reload --port 8001"
    )
    Done "Fenetre API ouverte"

    # ---------- 8. UI SvelteKit ----------
    if (-not $ApiOnly) {
        Step "UI SvelteKit -> http://localhost:5173"
        if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
            Write-Host "npm install (premiere fois, ~1 min)..."
            Push-Location (Join-Path $Root "frontend")
            & npm install --no-audit --no-fund
            $npmExit = $LASTEXITCODE
            Pop-Location
            if ($npmExit -ne 0) {
                Fail "npm install a echoue." "Voir la sortie ci-dessus ; verifier la version de Node (>= 20)."
            }
        }
        Start-Process powershell -ArgumentList @(
            "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
            "Set-Location '$Root\frontend'; Write-Host 'UI GxP Copilot (Ctrl+C pour arreter)' -ForegroundColor Cyan; npm run dev"
        )
        Start-Sleep -Seconds 3
        Start-Process "http://localhost:5173"
        Done "Fenetre UI ouverte, navigateur lance"
    }

    # ---------- Recapitulatif ----------
    Step "Pret"
    Write-Host "API  : http://localhost:8000   (GET /health, POST /ask)"
    if (-not $ApiOnly) { Write-Host "UI   : http://localhost:5173" }
    Write-Host "Log  : $LogFile"
    Write-Host "Stop : fermer les fenetres API/UI + 'docker compose down'"
    Write-Host ""
    Read-Host "Appuyez sur Entree pour fermer cette fenetre (API et UI restent ouvertes)"
}
catch {
    Fail "Exception inattendue : $($_.Exception.Message)" "Detail dans $LogFile (ligne $($_.InvocationInfo.ScriptLineNumber))."
}
