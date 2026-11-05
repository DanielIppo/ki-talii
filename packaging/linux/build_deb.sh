#!/usr/bin/env bash
set -e

# ==============================================================================
# Script di creazione pacchetto .deb per Linux (Debian, Ubuntu, Mint, Pop!_OS)
# ==============================================================================

RAW_VER="${1:-1.1}"
VERSION="${RAW_VER#v}"
PACKAGE_NAME="ki-talii"
ARCH="amd64"
DIST_DIR="$(pwd)/dist/ki-talii"
BUILD_ROOT="$(pwd)/packaging/linux/build_${PACKAGE_NAME}_${VERSION}_${ARCH}"
DEB_NAME="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"

echo "==> [1/4] Compilazione con PyInstaller su Linux..."
python3 -m pip install -r requirements.txt pyinstaller customtkinter pyyaml requests pillow
python3 -m PyInstaller --onedir --windowed --name "ki-talii" --add-data "assets:assets" --collect-all customtkinter --noconfirm gui.py

echo "==> [2/4] Preparazione struttura filesystem Debian..."
rm -rf "${BUILD_ROOT}"
mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/opt/${PACKAGE_NAME}"
mkdir -p "${BUILD_ROOT}/usr/bin"
mkdir -p "${BUILD_ROOT}/usr/share/applications"
mkdir -p "${BUILD_ROOT}/usr/share/icons/hicolor/256x256/apps"
mkdir -p "${BUILD_ROOT}/usr/share/pixmaps"

# Copia i binari compilati in /opt/ki-talii
cp -r "${DIST_DIR}/"* "${BUILD_ROOT}/opt/${PACKAGE_NAME}/"
cp config.example.yaml "${BUILD_ROOT}/opt/${PACKAGE_NAME}/"

# Copia icone per desktop e menu di sistema
cp assets/icon.png "${BUILD_ROOT}/usr/share/icons/hicolor/256x256/apps/ki-talii.png"
cp assets/icon.png "${BUILD_ROOT}/usr/share/pixmaps/ki-talii.png"

# Launcher eseguibile in /usr/bin/ki-talii
cat << 'EOF' > "${BUILD_ROOT}/usr/bin/ki-talii"
#!/bin/sh
exec /opt/ki-talii/ki-talii "$@"
EOF
chmod +x "${BUILD_ROOT}/usr/bin/ki-talii"

# File .desktop per menu applicazioni
cat << EOF > "${BUILD_ROOT}/usr/share/applications/ki-talii.desktop"
[Desktop Entry]
Name=ki-talii
Comment=Sincronizzatore ActivityWatcher e Kimai
Exec=/usr/bin/ki-talii
Icon=ki-talii
Terminal=false
Type=Application
Categories=Office;Development;Utility;
StartupNotify=true
EOF

# DEBIAN/control
cat << EOF > "${BUILD_ROOT}/DEBIAN/control"
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: DanielIppo <https://github.com/DanielIppo/ki-talii>
Depends: libc6, libx11-6
Description: Sincronizzazione automatica ActivityWatcher verso Kimai
 ki-talii traccia in automatico gli intervalli orari reali di lavoro
 rilevati da ActivityWatcher e li invia alle API di Kimai.
EOF

# DEBIAN/postinst
cat << 'EOF' > "${BUILD_ROOT}/DEBIAN/postinst"
#!/bin/sh
set -e
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q || true
fi
exit 0
EOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postinst"

echo "==> [3/4] Creazione del pacchetto .deb con dpkg-deb..."
dpkg-deb --build --root-owner-group "${BUILD_ROOT}" "${DEB_NAME}"

echo "==> [4/4] Pacchetto creato con successo!"
echo "File generato: $(pwd)/${DEB_NAME}"
ls -lh "${DEB_NAME}"
