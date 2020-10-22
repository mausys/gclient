# Copyright (c) 2016 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Note: to run this on e.g. OSX for adhoc testing or debugging in case Windows
# is not around:
#
# pwsh cipd.ps1 \
#     -CipdBinary _cipd.exe \
#     -BackendURL https://chrome-infra-packages.appspot.com \
#     -VersionFile ./cipd_client_version
# file _cipd.exe

Param(
  # Path to download the CIPD binary to.
  [parameter(Mandatory=$true)][string]$CipdBinary,
  # E.g. "https://chrome-infra-packages.appspot.com".
  [parameter(Mandatory=$true)][string]$BackendURL,
  # Path to the cipd_client_version file with the client version.
  [parameter(Mandatory=$true)][string]$VersionFile
)

$DepotToolsPath = Split-Path $MyInvocation.MyCommand.Path -Parent

if ([System.IntPtr]::Size -eq 8)  {
  $Platform = "windows-amd64"
} else {
  $Platform = "windows-386"
}

# Put depot_tool's git revision into the user agent string.
try {
  $DepotToolsVersion = &git -C $DepotToolsPath rev-parse HEAD 2>&1
  if ($LastExitCode -eq 0) {
    $UserAgent = "depot_tools/$DepotToolsVersion"
  } else {
    $UserAgent = "depot_tools/???"
  }
} catch [System.Management.Automation.CommandNotFoundException] {
  $UserAgent = "depot_tools/no_git/???"
}
$Env:CIPD_HTTP_USER_AGENT_PREFIX = $UserAgent


# Tries to delete the file, ignoring errors. Used for best-effort cleanups.
function Delete-If-Possible($path) {
  try {
    [System.IO.File]::Delete($path)
  } catch {
    $err = $_.Exception.Message
    echo "Warning: error when deleting $path - $err. Ignoring."
  }
}


# Returns the expected SHA256 hex digest for the given platform reading it from
# *.digests file.
function Get-Expected-SHA256($platform) {
  $digestsFile = $VersionFile+".digests"
  foreach ($line in Get-Content $digestsFile) {
    if ($line -match "^([0-9a-z\-]+)\s+sha256\s+([0-9a-f]+)$") {
      if ($Matches[1] -eq $platform) {
        return $Matches[2]
      }
    }
  }
  throw "No SHA256 digests for $platform in $digestsFile"
}


# Returns SHA256 hex digest of a binary file at the given path.
function Get-Actual-SHA256($path) {
  # Note: we don't use Get-FileHash to be compatible with PowerShell v3.0
  $file = [System.IO.File]::Open($path, [System.IO.FileMode]::Open)
  try {
    $algo = New-Object System.Security.Cryptography.SHA256Managed
    $hash = $algo.ComputeHash($file)
  } finally {
    $file.Close()
  }
  $hex = ""
  foreach ($byte in $hash) {
    $hex += $byte.ToString("x2")
  }
  return $hex
}


$ExpectedSHA256 = Get-Expected-SHA256 $Platform
$Version = (Get-Content $VersionFile).Trim()
$URL = "$BackendURL/client?platform=$Platform&version=$Version"


# Grab a lock to prevent simultaneous processes from stepping on each other.
# This depends on "exclusive write" file sharing mode used by OpenWrite.
$CipdLockPath = Join-Path $DepotToolsPath -ChildPath ".cipd_client.lock"
$CipdLockFile = $null
while ($CipdLockFile -eq $null) {
  try {
    $CipdLockFile = [System.IO.File]::OpenWrite($CipdLockPath)
  } catch [System.IO.IOException] {
    echo "CIPD bootstrap lock is held, trying again after delay..."
    Start-Sleep -s 1
  }
}

# Fetch the binary now that the lock is ours.
$TmpPath = $CipdBinary + ".tmp"
try {
  echo "Downloading CIPD client for $Platform from $URL..."
  $wc = (New-Object System.Net.WebClient)
  $wc.Headers.Add("User-Agent", $UserAgent)
  try {
    # Download failures were reported on Windows 8.1 without this line.
    [System.Net.ServicePointManager]::SecurityProtocol = `
            [System.Net.SecurityProtocolType]::Tls12
    $wc.DownloadFile($URL, $TmpPath)
  } catch {
    $err = $_.Exception.Message
    throw "Failed to download the file, check your network connection, $err"
  }

  $ActualSHA256 = Get-Actual-SHA256 $TmpPath
  if ($ActualSHA256 -ne $ExpectedSHA256) {
    throw "Invalid SHA256 digest: $ActualSHA256 != $ExpectedSHA256"
  }

  Move-Item -LiteralPath $TmpPath -Destination $CipdBinary -Force
} finally {
  $CipdLockFile.Close()
  Delete-If-Possible $CipdLockPath
  Delete-If-Possible $TmpPath
}
