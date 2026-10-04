param(
    [Parameter(Mandatory = $true)]
    [string]$User,

    [string]$HostName = "192.168.13.129",
    [int]$Port = 22,
    [string]$PackagePath = "build\huishi-vm-staging.tar.gz"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path -LiteralPath $PackagePath)) {
    throw "Package not found: $PackagePath"
}

$remotePackage = "/tmp/huishi-vm-staging.tar.gz"

scp -P $Port $PackagePath "${User}@${HostName}:$remotePackage"

$remoteCommand = @"
set -euo pipefail
sudo mkdir -p /opt/huishi
sudo tar -xzf $remotePackage -C /opt/huishi
sudo chown -R root:root /opt/huishi
sudo bash /opt/huishi/deploy/vm-staging-bootstrap.sh
"@

$remoteCommand | ssh -p $Port "${User}@${HostName}" "bash -s"
