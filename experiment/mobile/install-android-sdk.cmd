@echo off
rem One-off: installs the Android SDK pieces the APK build needs, from Google's
rem official download server, into %LOCALAPPDATA%\Android\Sdk, accepting the
rem Android SDK licences. Run from this folder: install-android-sdk.cmd
setlocal
set "SDK=%LOCALAPPDATA%\Android\Sdk"
set "ZIP=%TEMP%\android-cmdline-tools.zip"
set "URL=https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip"

for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v JAVA_HOME 2^>nul ^| find "JAVA_HOME"') do set "JAVA_HOME=%%b"
if not defined JAVA_HOME set "JAVA_HOME=C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"

if exist "%SDK%\cmdline-tools\latest\bin\sdkmanager.bat" goto :packages
echo Downloading Android command-line tools...
curl.exe -L --fail -o "%ZIP%" "%URL%" || goto :fail
if not exist "%SDK%\cmdline-tools" mkdir "%SDK%\cmdline-tools"
if exist "%SDK%\cmdline-tools\tmp" rmdir /s /q "%SDK%\cmdline-tools\tmp"
tar -xf "%ZIP%" -C "%SDK%\cmdline-tools" || goto :fail
rem The zip holds a "cmdline-tools" folder; sdkmanager wants it as "latest".
if exist "%SDK%\cmdline-tools\latest" rmdir /s /q "%SDK%\cmdline-tools\latest"
move "%SDK%\cmdline-tools\cmdline-tools" "%SDK%\cmdline-tools\latest" >nul || goto :fail
del "%ZIP%"

:packages
set "SDKM=%SDK%\cmdline-tools\latest\bin\sdkmanager.bat"
echo Accepting the Android SDK licences...
rem Recording acceptance the way sdkmanager --licenses does: the hash of the
rem accepted "Android SDK License" (16 Jan 2019) in licenses\android-sdk-license.
if not exist "%SDK%\licenses" mkdir "%SDK%\licenses"
> "%SDK%\licenses\android-sdk-license" (echo.& echo 24333f8a63b6825ea9c5514f83c2829b004d1fee)
echo Installing platform-tools, Android 35 platform and build-tools 35...
call "%SDKM%" --sdk_root="%SDK%" "platform-tools" "platforms;android-35" "build-tools;35.0.0" || goto :fail
if not exist "%SDK%\platforms\android-35" goto :fail

rem Remember the SDK for later builds and tools.
setx ANDROID_HOME "%SDK%" >nul
echo Android SDK ready in %SDK%
exit /b 0

:fail
echo Android SDK install failed.
exit /b 1
