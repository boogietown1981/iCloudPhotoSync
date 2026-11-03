SPK_NAME = icloudphotosync
SPK_VERS = 1.9.2
SPK_REV  = 1
SPK_ICON = src/PACKAGE_ICON.PNG

DEPENDS  = cross/heif-convert

UNSUPPORTED_ARCHS = $(OLD_PPC_ARCHS) $(ARMv5_ARCHS)

MAINTAINER     = Pascal Pagel
DESCRIPTION    = Automatically mirrors your iCloud photo library to a Synology NAS. Supports multi-account setups, incremental sync, album selection, HEIC conversion, and scheduled operation.
DISPLAY_NAME   = iCloud Photo Sync
CHANGELOG      = v1.9.2: fix DSM web CGI Python runtime selection and harden log initialization.

HOMEPAGE   = https://github.com/Euphonique/iCloudPhotoSync
LICENSE    = MIT

REQUIRED_MIN_DSM = 7.2
SERVICE_USER     = auto
STARTABLE        = yes
SERVICE_SETUP    = src/service-setup.sh

DSM_UI_DIR = app


PRE_COPY_TARGET = icloudphotosync_extra_install

include ../../mk/spksrc.spk.mk

.PHONY: icloudphotosync_extra_install
icloudphotosync_extra_install:
	@$(MSG) Installing iCloudPhotoSync application files
	@install -d -m 755 $(STAGING_INSTALL_PREFIX)/bin
	@install -d -m 755 $(STAGING_INSTALL_PREFIX)/lib
	@install -d -m 755 $(STAGING_INSTALL_PREFIX)/app
	@# Python application scripts
	@install -m 755 src/bin/scheduler.py $(STAGING_INSTALL_PREFIX)/bin/
	@install -m 755 src/bin/sync_runner.py $(STAGING_INSTALL_PREFIX)/bin/
	@install -m 755 src/bin/move_runner.py $(STAGING_INSTALL_PREFIX)/bin/
	@install -m 755 src/bin/integrity_runner.py $(STAGING_INSTALL_PREFIX)/bin/
	@# Python library modules
	@cp -R src/lib/*.py $(STAGING_INSTALL_PREFIX)/lib/
	@cp -R src/lib/handlers $(STAGING_INSTALL_PREFIX)/lib/
	@cp -R src/lib/vendor $(STAGING_INSTALL_PREFIX)/lib/
	@# Replace incomplete vendored HTTP packages with pinned, complete wheels.
	@rm -rf $(STAGING_INSTALL_PREFIX)/lib/vendor/requests \
	    $(STAGING_INSTALL_PREFIX)/lib/vendor/urllib3 \
	    $(STAGING_INSTALL_PREFIX)/lib/vendor/certifi \
	    $(STAGING_INSTALL_PREFIX)/lib/vendor/idna \
	    $(STAGING_INSTALL_PREFIX)/lib/vendor/charset_normalizer
	@python3 -m pip install --no-deps --no-compile --disable-pip-version-check \
	    --only-binary=:all: --platform any --implementation py --abi none \
	    --target $(STAGING_INSTALL_PREFIX)/lib/vendor -r src/requirements-pure.txt
	@cp -R src/app/* $(STAGING_INSTALL_PREFIX)/app/
	@# DSM configuration
	@install -d -m 755 $(STAGING_INSTALL_PREFIX)/conf
	@cp src/conf/privilege $(STAGING_INSTALL_PREFIX)/conf/
	@cp src/conf/resource $(STAGING_INSTALL_PREFIX)/conf/
