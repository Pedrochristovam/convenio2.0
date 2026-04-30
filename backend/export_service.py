import io
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from datetime import datetime
from typing import Dict, Any, List

class ExportService:
    """
    Handles generation of PDF and Excel reports for audit findings.
    """
    
    @staticmethod
    def generate_excel(data: Dict[str, Any]) -> io.BytesIO:
        """
        Generates a multi-sheet Excel file.
        """
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Resumos Mensais (Investimentos)
            if "resumos_mensais" in data:
                resumos = []
                for pag, info in data["resumos_mensais"].items():
                    row = {"Pagina": pag}
                    row.update(info["campos"])
                    resumos.append(row)
                df_resumos = pd.DataFrame(resumos)
                df_resumos.to_excel(writer, index=False, sheet_name="Resumos Investimento")
            
            # Sheet 2: Movimentações CC
            if "movimentacoes_cc" in data:
                df_cc = pd.DataFrame(data["movimentacoes_cc"])
                df_cc.to_excel(writer, index=False, sheet_name="Movimentacoes Conta Corrente")
                
            # Sheet 3: Glossário/Audit Info
            info_data = {
                "Campo": ["Data da Auditoria", "Metodo de Calculo", "Status"],
                "Valor": [datetime.now().strftime("%d/%m/%Y %H:%M"), data.get("metodoCalculo", "N/A"), "Concluido"]
            }
            pd.DataFrame(info_data).to_excel(writer, index=False, sheet_name="Informacoes")
            
        output.seek(0)
        return output

    @staticmethod
    def generate_pdf(data: Dict[str, Any]) -> io.BytesIO:
        """
        Generates a formal PDF Report using ReportLab.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        
        # Custom Styles
        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.navy, spaceAfter=20)
        subtitle_style = ParagraphStyle('SubtitleStyle', parent=styles['Heading2'], fontSize=14, textColor=colors.darkblue, spaceAfter=10)
        normal_style = styles['Normal']
        
        elements = []
        
        # 1. Header
        elements.append(Paragraph("PARECER TÉCNICO DE AUDITORIA FINANCEIRA", title_style))
        elements.append(Paragraph(f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal_style))
        elements.append(Spacer(1, 1*cm))
        
        # 2. Executive Summary Item
        elements.append(Paragraph("1. RESUMO EXECUTIVO", subtitle_style))
        summary_text = (
            f"Este parecer apresenta os resultados da auditoria automatizada do convênio. "
            f"O método de correção utilizado para glosas foi <b>{data.get('metodoCalculo', 'N/A').upper()}</b>."
        )
        elements.append(Paragraph(summary_text, normal_style))
        elements.append(Spacer(1, 0.5*cm))
        
        # 3. Tables (Monthly Summaries)
        if "resumos_mensais" in data:
            elements.append(Paragraph("2. LANÇAMENTOS DO EXTRATO DE INVESTIMENTO", subtitle_style))
            
            table_data = [["Pág.", "Saldo Ant.", "Resgates", "Rendimento", "Saldo Atual"]]
            # Limit to first 20 for brevity or show all
            for pag, info in list(data["resumos_mensais"].items()):
                c = info["campos"]
                table_data.append([
                    str(pag),
                    f"R$ {c.get('saldo_anterior', 0):,.2f}",
                    f"R$ {c.get('resgates', 0):,.2f}",
                    f"R$ {c.get('rendimento_bruto', 0):,.2f}",
                    f"R$ {c.get('saldo_atual', 0):,.2f}"
                ])
                
            t = Table(table_data, colWidths=[1.5*cm, 3.5*cm, 3.5*cm, 3.5*cm, 3.5*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
            ]))
            elements.append(t)
            elements.append(Spacer(1, 1*cm))

        # 4. Final Considerations
        elements.append(Paragraph("3. CONCLUSÃO E RECOMENDAÇÕES", subtitle_style))
        elements.append(Paragraph(
            "Com base nos lançamentos identificados, recomenda-se a restituição imediata dos valores "
            "de rendimentos e saldos remanescentes à conta da União, devidamente atualizados.", 
            normal_style
        ))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer

# Singleton instance
export_service = ExportService()
