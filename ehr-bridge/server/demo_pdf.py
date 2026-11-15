"""Small dependency-free PDF reports for the synthetic demo dataset."""
import textwrap
import unicodedata


def _ascii(value):
    return unicodedata.normalize('NFKD', str(value)).encode('ascii', 'replace').decode('ascii')


def make_report(title, patient, hospital, doctor, visit_date, sections):
    lines = []
    for label, content in sections:
        lines.append((_ascii(label).upper(), True))
        for paragraph in str(content).splitlines():
            lines.extend((line, False) for line in textwrap.wrap(_ascii(paragraph), 93))
        lines.append(('', False))
    pages = [lines[index:index + 38] for index in range(0, len(lines), 38)] or [[]]
    objects = [b'', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>']
    page_ids = []

    def escape(value):
        return _ascii(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    for number, page in enumerate(pages, 1):
        commands = ['0.08 0.35 0.38 rg 0 738 612 54 re f']

        def text(x, y, value, size=10, bold=False, white=False):
            color = '1 1 1' if white else '0.15 0.23 0.28'
            commands.append(f'{color} rg BT /{"F2" if bold else "F1"} {size} Tf {x} {y} Td ({escape(value)}) Tj ET')

        text(38, 764, hospital, 17, True, True)
        text(38, 746, 'SYNTHETIC HOSPITAL RECORD - DEMONSTRATION ONLY', 9, False, True)
        for index, line in enumerate(textwrap.wrap(_ascii(title), 83)[:2]):
            text(38, 715 - index * 16, line, 12, True)
        text(38, 674, f'Patient: {patient["name"]} | DOB: {patient["birth_date"]}', 10)
        text(38, 657, f'Patient ID: {patient["id"]} | Clinical date: {visit_date}', 10)
        text(38, 640, f'Recorded by: {doctor}', 10)
        y = 613
        for line, bold in page:
            if line:
                text(38, y, line, 9, bold)
            y -= 13.5
        text(38, 58, 'All identities, observations and notes in this report are invented for software demonstration.', 8)
        text(38, 43, f'Not for diagnosis, prescribing or clinical decisions. Page {number} of {len(pages)}.', 8)
        stream = '\n'.join(commands).encode('ascii')
        page_id, stream_id = len(objects) + 1, len(objects) + 2
        page_ids.append(page_id)
        objects.extend([
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>'.encode(),
            f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream',
        ])
    objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(str(pid) + " 0 R" for pid in page_ids)}] /Count {len(page_ids)} >>'.encode()
    output = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(output)
    output.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    for offset in offsets:
        output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(output)
