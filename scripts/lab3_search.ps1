param(
    [string]$GroupName
)

if (-not $GroupName) { $GroupName = Read-Host "Введите название группы (например, БСБО-01-23)" }

# 1. Получение токена
$tokenBody = @{
    grant_type = "password"
    username   = "admin"
    password   = "secret"
}
try {
    $tokenResponse = Invoke-RestMethod -Uri "http://localhost:8000/token" -Method Post -Body $tokenBody -ContentType "application/x-www-form-urlencoded"
    $token = $tokenResponse.access_token
} catch {
    Write-Host "Ошибка получения токена: $_" -ForegroundColor Red
    exit 1
}

# 2. Запрос отчёта
$encodedGroup = [uri]::EscapeDataString($GroupName)
$url = "http://localhost:8000/api/lab3/report?group_name=$encodedGroup"

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

$report = $json | ConvertFrom-Json

# 3. Формирование текстового отчёта
$lines = @()
$lines += "=" * 165
$lines += "ОТЧЁТ: Объём прослушанных и запланированных часов по группе $GroupName"
$lines += "=" * 165
$lines += "Параметры запроса:"
$lines += "  Группа:                   $GroupName"

# Университет из MongoDB (если есть)
if ($report.university) {
    $lines += "  Университет:             $($report.university.name)"
    $lines += "  Адрес:                    $($report.university.address)"
    $lines += "  Сайт:                     $($report.university.website)"
}

if ($report.students.Count -eq 0) {
    $lines += "`nНет данных. Возможно, не выполнена генерация или для указанной группы нет специальных дисциплин кафедры."
} else {
    $lines += "`nСтудентов в отчёте: $($report.students.Count)"
    $lines += ""
    $lines += "-" * 165
    $lines += ("{0,-3} {1,-35} {2,-25} {3,-15} {4,-15}" -f "№", "ФИО студента", "Курс", "Запланировано", "Прослушано")
    $lines += "-" * 165

    foreach ($student in $report.students) {
        $fullName = "$($student.last_name) $($student.first_name) $($student.patronymic)".Trim()
        if ($fullName.Length -gt 35) { $fullName = $fullName.Substring(0, 32) + "..." }

        if ($student.courses.Count -eq 0) {
            $lines += ("{0,-3} {1,-35} {2,-25} {3,-15} {4,-15}" -f "–", $fullName, "–", "–", "–")
        } else {
            $courseNum = 1
            foreach ($course in $student.courses) {
                $courseName = if ($course.course_name.Length -gt 25) { $course.course_name.Substring(0, 22) + "..." } else { $course.course_name }
                $planned = $course.planned_hours
                $attended = $course.attended_hours
                $lines += ("{0,-3} {1,-35} {2,-25} {3,-15} {4,-15}" -f $courseNum, $fullName, $courseName, $planned, $attended)
                $courseNum++
                $fullName = ""   # не повторяем ФИО для следующих курсов
            }
        }
        $lines += ""   # пустая строка между студентами
    }

    $lines += "-" * 165
    $lines += ""
    $lines += "=" * 165
    $lines += "Использованные хранилища данных:"
    $lines += "  - PostgreSQL: группы, кафедральные курсы, посещаемость"
    $lines += "  - Neo4j: граф связей групп со студентами и расписанием"
    $lines += "  - Redis: персональные данные студентов (ФИО, контакты)"
    $lines += "  - MongoDB: информация об университете"
    $lines += "=" * 165
}

# 4. Сохранение в файл (UTF-8 без BOM)
$reportFile = Join-Path -Path $PSScriptRoot -ChildPath "report.txt"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($reportFile, $lines, $utf8NoBom)

Write-Host "Отчёт сохранён в файл: $reportFile" -ForegroundColor Green