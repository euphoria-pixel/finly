# TLS Т-Банка

`russian_trusted_root_ca.pem` получен 26.09.2026 по HTTPS:
https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt

SHA-256 сертификата (DER):
D2:6D:2D:02:31:B7:C3:9F:92:CC:73:85:12:BA:54:10:35:19:E4:40:5D:68:B5:BD:70:3E:97:88:CA:8E:CF:31

Используется только отдельным SSLContext клиента T-API Sandbox.
Системное хранилище сертификатов не изменяется. TLS-проверка не отключается.
Другой доверенный PEM можно указать через TBANK_CA_FILE.
