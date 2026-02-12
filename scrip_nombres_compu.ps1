# ---------------------------
# Script: Inventario Seriales WMI (sin WinRM)
# Autor: Pablo + Copilot 😄
# ---------------------------

# Lista de equipos
$PCs = @(
"MROD000256",
"MROD000257",
"MROD000258",
"MROD000259",
"MROD000260",
"MROD000261",
"MROD000262",
"MROD000264",
"MROD000265",
"MROD000266",
"MROD000267",
"MROD000269",
"MROD000271",
"MROD000272",
"MROD000273",
"MROD000275",
"MROD000276",
"MROD000277",
"MROD000278",
"MROD000279",
"MROD000280",
"MROD000282",
"MROD000283",
"MROD000284",
"MROD000285",
"MROD000287",
"MROD000291",
"MROD000491",
"MRON000362"
)

# Lista para guardar resultados
$Resultados = @()

foreach ($PC in $PCs) {

    Write-Host "Consultando $PC ..." -ForegroundColor Cyan

    # 1. Test de ping
    $ping = Test-Connection -ComputerName $PC -Count 1 -Quiet -ErrorAction SilentlyContinue

    if (-not $ping) {
        # PC apagada o fuera de red
        $Resultados += [PSCustomObject]@{
            Equipo   = $PC
            Serial   = "N/A"
            Modelo   = "N/A"
            Usuario  = "N/A"
            Estado   = "Sin respuesta (Ping FAIL)"
        }
        continue
    }

    # 2. Consultar WMI
    try {
        $bios = Get-WmiObject -Class Win32_BIOS -ComputerName $PC -ErrorAction Stop
        $cs   = Get-WmiObject -Class Win32_ComputerSystem -ComputerName $PC -ErrorAction Stop

        $Resultados += [PSCustomObject]@{
            Equipo   = $PC
            Serial   = $bios.SerialNumber
            Modelo   = $cs.Model
            Usuario  = $cs.UserName
            Estado   = "OK"
        }
    }
    catch {
        # Error WMI: no accesible, DCOM bloqueado, permisos, etc.
        $Resultados += [PSCustomObject]@{
            Equipo   = $PC
            Serial   = "N/A"
            Modelo   = "N/A"
            Usuario  = "N/A"
            Estado   = "Error WMI: $($_.Exception.Message)"
        }
    }
}

# Mostrar resultados en pantalla
$Resultados | Format-Table -AutoSize

# Exportar a CSV en el escritorio
$Path = "$env:USERPROFILE\Desktop\Inventario_Seriales_WMI.csv"
$Resultados | Export-Csv -Path $Path -NoTypeInformation -Encoding UTF8

Write-Host "`nArchivo generado en:" $Path -ForegroundColor Green
Write-Host "Proceso finalizado." -ForegroundColor Yellow