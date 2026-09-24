"""QR Code do Pix a partir do código copia e cola.

Dependência opcional: `qrcode` (a mesma versão do Cointex, 8.2). Sem ela, e sem imagem vinda do provedor,
a tela mostra só o copia e cola.
"""
import base64
import io


def pix_qr_data_uri(code):
    if not code:
        return ""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return ""
    image = qrcode.make(code, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_M)
    buffer = io.BytesIO()
    image.save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()


def safe_image_src(value):
    """Só aceita imagem em data URI ou https (nada de javascript: ou caminhos arbitrários)."""
    value = str(value or "")
    return value if value.startswith(("data:image/", "https://")) else ""
