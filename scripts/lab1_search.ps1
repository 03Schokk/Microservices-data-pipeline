param(
    [string]$Term,
    [string]$StartDate,
    [string]$EndDate
)

if (-not $Term) { $Term = Read-Host "Введите термин" }
if (-not $StartDate) { $StartDate = "2024-09-01" }
if (-not $EndDate) { $EndDate = "2024-12-24" }

Write-Host "Искомый термин: $Term"

# 1. Получение токена
$tokenBody = @{
    grant_type = "password"
    username   = "admin"
    password   = "secret"
}
$tokenResponse = Invoke-RestMethod -Uri "http://localhost:8000/token" -Method Post -Body $tokenBody -ContentType "application/x-www-form-urlencoded"
$token = $tokenResponse.access_token

# 2. Формирование URL и запрос к отчёту
$encodedTerm = [uri]::EscapeDataString($Term)
$url = "http://localhost:8000/api/lab1/report?term=$encodedTerm&start_date=$StartDate&end_date=$EndDate"

# Используем .NET HttpWebRequest, чтобы контролировать кодировку
$req = [System.Net.WebRequest]::Create($url)
$req.Method = "POST"
$req.Headers.Add("Authorization", "Bearer $token")
$req.ContentType = "application/x-www-form-urlencoded"
$req.ContentLength = 0

try {
    $resp = $req.GetResponse()
    $stream = $resp.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
    $json = $reader.ReadToEnd()
    $reader.Close()
    $resp.Close()
} catch {
    Write-Host "Ошибка при запросе отчёта: $_" -ForegroundColor Red
    exit 1
}

# Преобразуем JSON в объект (теперь строки в UTF-8, кириллица корректна)
$report = $json | ConvertFrom-Json

# 3. Формирование отчёта в виде массива строк
$lines = @()
$lines += "=" * 165
$lines += "ОТЧЁТ: 10 студентов с минимальным процентом посещения лекций, содержащих термин"
$lines += "=" * 165
$lines += "Параметры отчёта:"
$lines += "  Термин:                     '$Term'"
$lines += "  Период:                     $StartDate – $EndDate"

if ($report.students.Count -gt 0 -and $report.students[0].university) {
    $uni = $report.students[0].university
    $lines += "  Университет (MongoDB):     $($uni.name)"
    $lines += "  Адрес:                     $($uni.address)"
}

$lines += "`nРезультаты:"
$lines += "-" * 165

if ($report.students.Count -eq 0) {
    $lines += "Нет данных. Возможно, не выполнена генерация или термин не найден."
} else {
    $fmt = "{0,-35} {1,-12} {2,-20} {3,-20} {4,-12} {5,-35} {6,-12} {7,-12}"
    $lines += ($fmt -f "Студент", "Номер карты", "Email", "Телефон", "Группа", "Специальность", "Посещ. %", "Занятий")
    $lines += "-" * 165
    foreach ($s in $report.students) {
        $fullName = "$($s.last_name) $($s.first_name) $($s.patronymic)".Trim()
        if ($fullName.Length -gt 35) { $fullName = $fullName.Substring(0, 32) + "..." }
        $card = $s.student_card_number
        $email = if ($s.email.Length -gt 20) { $s.email.Substring(0, 17) + "..." } else { $s.email }
        $phone = if ($s.phone.Length -gt 20) { $s.phone.Substring(0, 17) + "..." } else { $s.phone }
        $group = $s.group_name
        $spec = $s.specialty_name
        if ($spec.Length -gt 35) { $spec = $spec.Substring(0, 32) + "..." }
        $percent = "{0:F2} %" -f $s.attendance_percent
        $total = $s.total_scheduled
        $lines += ($fmt -f $fullName, $card, $email, $phone, $group, $spec, $percent, $total)
    }
    $lines += "-" * 165
    $lines += "`n" + "=" * 165
    $lines += "Отчёт сформирован с использованием всех пяти БД:"
    $lines += "  - Elasticsearch: поиск лекций по тексту"
    $lines += "  - Neo4j: расписание, группы, студенты (граф)"
    $lines += "  - PostgreSQL: расчёт посещаемости"
    $lines += "  - Redis: персональные данные студентов"
    $lines += "  - MongoDB: информация об университете"
    $lines += "=" * 165
}

# 4. Сохранение в файл (UTF-8 без BOM)
$reportFile = Join-Path -Path $PSScriptRoot -ChildPath "report.txt"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($reportFile, $lines, $utf8NoBom)

Write-Host "Отчёт сохранён в файл: $reportFile" -ForegroundColor Green