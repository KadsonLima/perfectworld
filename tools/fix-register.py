"""Patch confirmed defects in the registration file extracted from the pinned image."""
from pathlib import Path
import datetime
import shutil
import json

root = Path(__file__).resolve().parents[1]
source = root / 'audit/images/website-register/files/var/www/html/register.php'
backup = root / 'backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup.mkdir(parents=True)
shutil.copy2(source, backup / 'register.php')
shutil.copy2(root / 'docker-compose.yaml', backup / 'docker-compose.yaml')
text = source.read_text()
text = text.replace("StrPos('\\'', $Email)", "strpos($Email, \"'\") !== false || !filter_var($Email, FILTER_VALIDATE_EMAIL)")
text = text.replace("SELECT name FROM users WHERE name='$Email'", "SELECT name FROM users WHERE email='" + "$Email'" )
text = text.replace("'0', '', '', '$Salt')", "'0', NULL, '', '$Salt')")
text = text.replace('$Salt = base64_encode', '$Email = mysql_real_escape_string($Email, $link);\n\t\t\t\t$Salt = base64_encode')
dest = root / 'configs/website-register/register.php'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(text, newline='\n')
compose = json.loads((root / 'docker-compose.yaml').read_text())
compose['services']['perfectworld-website-register'].setdefault('volumes', []).append({'type': 'bind', 'source': './configs/website-register/register.php', 'target': '/var/www/html/register.php', 'read_only': True})
(root / 'docker-compose.yaml').write_text(json.dumps(compose, indent=2) + '\n', newline='\n')
print('Registration backup:', backup)
