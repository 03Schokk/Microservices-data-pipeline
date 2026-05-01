param(
    [int]$Semester,
    [int]$Year
)

if (-not $Semester) { $Semester = Read-Host "Введите номер семестра" }
if (-not $Year) { $Year = Read-Host "Введите год набора студентов" }

# 1. Получение токена
$tokenBody = @{
    grant_type = "password"
    username   = "admin"
    password   = "secret"
}
$tokenResponse = Invoke-RestMethod -Uri "http://localhost:8000/token" -Method Post -Body $tokenBody -ContentType "application/x-www-form-urlencoded"
$token = $tokenResponse.access_token

# 2. Запрос отчёта
$url = "http://localhost:8000/api/lab2/report?semester=$Semester&year=$Year"
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
    Write-Host "Ошибка при запросе: $_" -ForegroundColor Red
    exit 1
}

$report = $json | ConvertFrom-Json

# 3. Формирование отчета
$lines = @()
$lines += "=" * 165
$lines += "ОТЧЁТ: Аудиторная нагрузка по курсам $Semester семестра (год набора $Year)"
$lines += "=" * 165
$lines += "Параметры запроса:"
$lines += "  Семестр:               $Semester"
$lines += "  Год набора:            $Year"
$lines += ""

if ($report.lectures.Count -eq 0) {
    $lines += "Нет данных. Возможно, не выполнена генерация или для указанных параметров нет лекций."
} else {
    $lines += "-" * 185
    $lines += ("{0,-22} {1,-25} {2,-30} {3,-10} {4,-30} {5,-10} {6,-35}" -f 
            "Специальность", "Курс", "Лекция", "Тип", "Требования к оборуд.", "Студ.", "Описание курса")
    $lines += "-" * 185

    foreach ($lec in $report.lectures) {
        $spec   = if ($lec.specialty_name.Length -gt 22) { $lec.specialty_name.Substring(0, 19) + "..." } else { $lec.specialty_name }
        $course = if ($lec.course_name.Length -gt 25) { $lec.course_name.Substring(0, 22) + "..." } else { $lec.course_name }
        $title  = if ($lec.lecture_title.Length -gt 30) { $lec.lecture_title.Substring(0, 27) + "..." } else { $lec.lecture_title }
        $type   = $lec.lecture_type
        $equip  = if ($lec.computer_type.Length -gt 30) { $lec.computer_type.Substring(0, 27) + "..." } else { $lec.computer_type }
        $count  = $lec.student_count
        $desc   = if ($lec.course_description.Length -gt 35) { $lec.course_description.Substring(0, 32) + "..." } else { $lec.course_description }
        $lines += ("{0,-22} {1,-25} {2,-30} {3,-10} {4,-30} {5,-10} {6,-35}" -f $spec, $course, $title, $type, $equip, $count, $desc)
    }

    $lines += "-" * 185
    $lines += "Всего лекций: $($report.lectures.Count)"
    $lines += ""
    $lines += "=" * 165
    $lines += "Использованные хранилища данных:"
    $lines += "  - PostgreSQL: курсы, лекции, группы по году набора"
    $lines += "  - Neo4j: граф связей групп со студентами и расписанием"
    $lines += "=" * 165
}

# 4. Сохранение в файл (UTF-8)
$reportFile = Join-Path -Path $PSScriptRoot -ChildPath "report.txt"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($reportFile, $lines, $utf8NoBom)

Write-Host "Отчёт сохранён в файл: $reportFile" -ForegroundColor Green