param(
    [Parameter(Mandatory = $true)]
    [string]$CodeFile,
    [int]$Port = 9876
)

$ErrorActionPreference = 'Stop'
$code = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $CodeFile))
$payload = @{
    type = 'execute_code'
    params = @{ code = $code }
} | ConvertTo-Json -Depth 6 -Compress

$client = [System.Net.Sockets.TcpClient]::new()
try {
    $client.Connect('127.0.0.1', $Port)
    $stream = $client.GetStream()
    $stream.ReadTimeout = 30000

    $request = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $stream.Write($request, 0, $request.Length)

    $buffer = New-Object byte[] 65536
    $response = [System.Text.StringBuilder]::new()
    $read = $stream.Read($buffer, 0, $buffer.Length)
    [void]$response.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $read))

    Start-Sleep -Milliseconds 150
    while ($stream.DataAvailable) {
        $read = $stream.Read($buffer, 0, $buffer.Length)
        [void]$response.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $read))
    }

    $response.ToString()
}
finally {
    $client.Dispose()
}
