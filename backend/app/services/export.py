from typing import List, Dict, Any
import csv
import io
import xlsxwriter
from datetime import datetime
from fastapi import HTTPException
from app.models.business_data import BusinessData

class ExportService:
    @staticmethod
    def _get_business_data(businesses: List[BusinessData]) -> List[Dict[str, Any]]:
        return [{
            "Name": business.name,
            "Address": business.formatted_address,
            "Phone": business.formatted_phone_number or "N/A",
            "Website": business.website or "N/A",
            "Rating": str(business.rating or "N/A"),
            "Total Ratings": str(business.user_ratings_total or "N/A"),
            "Price Level": "€" * int(business.price_level or 0) if business.price_level else "N/A",
            "Status": business.business_status or "N/A",
            "Categories": ", ".join(business.types) if business.types else "N/A",
            "Latitude": business.latitude,
            "Longitude": business.longitude
        } for business in businesses]

    @staticmethod
    def to_csv(businesses: List[BusinessData]) -> bytes:
        if not businesses:
            raise HTTPException(status_code=404, detail="No data to export")

        output = io.StringIO()
        data = ExportService._get_business_data(businesses)
        
        writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)
        
        return output.getvalue().encode('utf-8')

    @staticmethod
    def to_xlsx(businesses: List[BusinessData]) -> bytes:
        if not businesses:
            raise HTTPException(status_code=404, detail="No data to export")

        output = io.BytesIO()
        data = ExportService._get_business_data(businesses)
        
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet("Business Data")
        
        headers = list(data[0].keys())
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#f0f0f0',
            'border': 1
        })
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
            worksheet.set_column(col, col, max(len(header) * 1.2, 15))
        
        cell_format = workbook.add_format({
            'border': 1,
            'text_wrap': True
        })
        
        for row, business in enumerate(data, start=1):
            for col, field in enumerate(headers):
                worksheet.write(row, col, business[field], cell_format)
        
        workbook.close()
        return output.getvalue()

    @staticmethod
    def generate_filename(search_type: str, format: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        search_type = search_type.replace(" ", "_").lower()
        return f"business_search_{search_type}_{timestamp}.{format}"