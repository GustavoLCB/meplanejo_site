import re

from django.db import migrations


def colocar_dois_pontos(apps, schema_editor):
    """'Entenda como funciona CDB' -> 'Entenda como funciona: CDB'."""
    Card = apps.get_model('MEPLANEJO', 'CardInvestimento')
    for card in Card.objects.all():
        novo = re.sub(r'^Entenda como funciona(?!:)\s+', 'Entenda como funciona: ', card.descricao)
        if novo != card.descricao:
            card.descricao = novo
            card.save(update_fields=['descricao'])


class Migration(migrations.Migration):

    dependencies = [
        ('MEPLANEJO', '0010_remove_url_video_normaliza_tipos'),
    ]

    operations = [
        migrations.RunPython(colocar_dois_pontos, migrations.RunPython.noop),
    ]
