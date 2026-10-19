@echo off
rem Builds the Bayut Valuations Android app (debug-signed APK) and copies it to
rem Downloads. Needs JDK 21 and the Android SDK. Run from this folder: build-apk.cmd
setlocal
cd /d "%~dp0"

rem Use the JDK and SDK set for your user account; fall back to the usual paths.
for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v JAVA_HOME 2^>nul ^| find "JAVA_HOME"') do set "JAVA_HOME=%%b"
for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v ANDROID_HOME 2^>nul ^| find "ANDROID_HOME"') do set "ANDROID_HOME=%%b"
if not defined ANDROID_HOME set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "PATH=%JAVA_HOME%\bin;%PATH%"

if not exist node_modules call npm install --no-fund --no-audit || goto :fail
call npx cap sync android || goto :fail

call "%~dp0android\gradlew.bat" -p "%~dp0android" assembleDebug --console=plain
if errorlevel 1 goto :fail
cd /d "%~dp0"

copy /y "android\app\build\outputs\apk\debug\app-debug.apk" "%USERPROFILE%\Downloads\BayutValuations.apk" >nul || goto :fail
echo APK ready: %USERPROFILE%\Downloads\BayutValuations.apk
exit /b 0

:fail
echo APK build failed.
exit /b 1
