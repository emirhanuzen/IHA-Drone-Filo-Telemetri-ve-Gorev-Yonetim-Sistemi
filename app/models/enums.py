import enum


class DroneStatus(str, enum.Enum):
    """Drone durumu."""

    AKTIF = "aktif"
    BAKIMDA = "bakimda"
    GOREVDE = "gorevde"


class MissionStatus(str, enum.Enum):
    """Görev durumu."""

    PLANLANDI = "planlandi"
    DEVAM_EDIYOR = "devam_ediyor"
    TAMAMLANDI = "tamamlandi"
    IPTAL = "iptal"


class AlertType(str, enum.Enum):
    """Sensör uyarı tipi."""

    DUSUK_YAKIT = "dusuk_yakit"
    ANOMALI = "anomali"
    SINYAL_KAYBI = "sinyal_kaybi"


class AlertSeverity(str, enum.Enum):
    """Uyarının önem derecesi."""

    DUSUK = "dusuk"
    ORTA = "orta"
    YUKSEK = "yuksek"
    KRITIK = "kritik"


class UserRole(str, enum.Enum):
    """Kullanıcı rolleri."""

    ADMIN = "admin"
    COMMANDER = "commander"
    OPERATOR = "operator"
    ANALYST = "analyst"
