import os
import re
import json
import time
import urllib.parse
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from dynamic_engine import (
    get_country_top_10,
    get_country_jobs_top_10,
    live_web_search_contacts,
    live_web_search_jobs,
    SKILL_TRANSLATIONS,
    PRODUCT_TRANSLATIONS,
    COUNTRY_DIRECTORIES,
    COUNTRY_JOB_DIRECTORIES
)

app = FastAPI(title="Global B2B & Career Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HS_CODE_DATABASE = {
    "سیب": {
        "hs_code": "0808.10",
        "title_en": "Fresh Apples (Malus domestica)",
        "packaging": "کارتن‌های تلسکوپی صادراتی ۳ لایه یا ۵ لایه / سبدهای پلی‌اتیلنی محکم با شانه فومی (۱۰ تا ۱۸ کیلو)",
        "reefer_temp": "۰ الی ۲+ درجه سانتی‌گراد با رطوبت نسبی ۹۰-۹۵٪ (کانتینر یخچالی با تهویه ۲۵ CFM)",
        "shelf_life": "۴ تا ۶ ماه در سردخانه اتمسفر کنترل‌شده (CA)، ۲ تا ۳ هفته در حمل جاده‌ای",
        "documents": [
            "گواهی بهداشت نباتی (Phytosanitary Certificate) از حفظ نباتات",
            "گواهی مبدأ (Certificate of Origin) از اتاق بازرگانی",
            "بارنامه بین‌المللی ترانزیت (CMR / Bill of Lading)",
            "فاکتور رسمی و پکینگ لیست (Commercial Invoice & Packing List)",
            "گواهی سم‌شناسی و عدم باقیمانده آفت‌کش‌ها (Residue Test)"
        ],
        "key_markets": "عراق (تمرچین و پرویزخان)، هند (بندر ناواشیوا)، روسیه (بندر آستاراخان)، امارات (دبی)"
    },
    "سیب‌زمینی": {
        "hs_code": "0701.90",
        "title_en": "Fresh Potatoes (Solanum tuberosum)",
        "packaging": "گونی‌های توری راشل (Rachel Bags) یا کیسه‌های اسپانیایی تهویه‌دار ۲۵ تا ۳۰ کیلویی",
        "reefer_temp": "۴ الی ۸+ درجه سانتی‌گراد (نباید زیر ۴ درجه برود تا نشاسته به قند تبدیل نشود)",
        "shelf_life": "۳ تا ۵ ماه در محیط خشک، تاریک و خنک",
        "documents": [
            "گواهی قرنطینه و عدم آلودگی به نماتد طلایی (Golden Nematode-Free)",
            "گواهی سلامت نباتی سازمان جهاد کشاورزی",
            "گواهی مبدأ اتاق بازرگانی",
            "فاکتور تجاری و پکینگ لیست"
        ],
        "key_markets": "عراق، افغانستان، آذربایجان، روسیه، ترکمنستان"
    },
    "کیوی": {
        "hs_code": "0810.50",
        "title_en": "Fresh Kiwifruit (Actinidia deliciosa - Hayward)",
        "packaging": "کارتن تک‌ردیفه با شانه پلاستیکی ۳ تا ۴ کیلو یا سبدهای دوقلو ۱۰ کیلویی",
        "reefer_temp": "۰ الی ۰.۵- درجه سانتی‌گراد (بسیار حساس به گاز اتیلن، فیلتر اتیلن الزامی است)",
        "shelf_life": "۳ تا ۴ ماه در سردخانه، ۳۰ روز در کانتینر یخچالی",
        "documents": [
            "گواهی قند بریکس (حداقل ۶.۲ هنگام برداشت و بالای ۱۲ هنگام تحویل)",
            "گواهی بهداشت نباتی",
            "گواهی مبدأ و پکینگ لیست عدل‌بندی"
        ],
        "key_markets": "هندوستان، امارات، روسیه، قزاقستان"
    },
    "خرما": {
        "hs_code": "0804.10",
        "title_en": "Fresh or Dried Dates (Mazafati, Piarom, Zahedi)",
        "packaging": "جعبه‌های مادر ۵۰۰ گرمی در کارتن‌های ۵ کیلویی (مضافتی) یا فله ۱۰ کیلویی (زاهدی)",
        "reefer_temp": "۴ الی ۵- درجه سانتی‌گراد برای مضافتی تازه | دمای محیط خنک برای پیارم و زاهدی خشک",
        "shelf_life": "۱۲ تا ۱۸ ماه",
        "documents": [
            "گواهی بهداشت غذا و دارو (FDA / Health Certificate)",
            "گواهی حلال (Halal Certificate)",
            "گواهی بهداشت نباتی و ضدعفونی گاز متیل بروماید (Fumigation Certificate)",
            "گواهی استاندارد اجباری ایران"
        ],
        "key_markets": "هندوستان، ترکیه، روسیه، مالزی، آلمان، امارات"
    },
    "پسته": {
        "hs_code": "0802.51",
        "title_en": "Pistachios in Shell (Akbari, Ahmad Aghaei, Fandoghi)",
        "packaging": "کیسه‌های پروپیلن ۲۵ و ۵۰ کیلویی یا کارتن‌های لمینت ۱۰ کیلویی وکیوم",
        "reefer_temp": "۵ الی ۱۰+ درجه سانتی‌گراد در محیط کاملاً خشک (رطوبت زیر ۶۵٪)",
        "shelf_life": "۱۲ تا ۲۴ ماه",
        "documents": [
            "گواهی معتبر آزمایشگاهی عدم وجود آفلاتوکسین (Aflatoxin B1 & Total زیر حد مجاز اتحادیه اروپا/حوزه خلیج)",
            "گواهی مبدأ و استاندارد صادراتی",
            "گواهی ضدعفونی و بهداشت نباتی"
        ],
        "key_markets": "آلمان و اتحادیه اروپا، چین، امارات، هند، ترکیه"
    },
    "گوجه": {
        "hs_code": "0702.00",
        "title_en": "Fresh Tomatoes (Greenhouse & Field)",
        "packaging": "سبدهای پلاستیکی ۵ تا ۷ کیلویی با فوم ضدضربه یا کارتن‌های مقاوم صادراتی",
        "reefer_temp": "۸ الی ۱۲+ درجه سانتی‌گراد (سرمازدگی زیر ۷ درجه باعث فساد بافت می‌شود)",
        "shelf_life": "۱۰ الی ۱۵ روز",
        "documents": [
            "گواهی عدم آلودگی به ویروس چروکیدگی قهوه‌ای گوجه (ToBRFV-Free)",
            "گواهی بهداشت نباتی",
            "گواهی مبدأ و CMR"
        ],
        "key_markets": "عراق، روسیه، امارات، قطر، عمان"
    },
    "پیاز": {
        "hs_code": "0703.10",
        "title_en": "Fresh Onions (Yellow, Red, White)",
        "packaging": "کیسه‌های توری راشل ۲۰ و ۲۵ کیلویی تهویه‌دار",
        "reefer_temp": "۰ الی ۴+ درجه سانتی‌گراد با تهویه هوای خشک (رطوبت بالا باعث جوانه‌زنی می‌شود)",
        "shelf_life": "۲ تا ۴ ماه",
        "documents": [
            "گواهی سلامت نباتی سازمان جهاد کشاورزی",
            "گواهی مبدأ اتاق بازرگانی",
            "بارنامه و پکینگ لیست"
        ],
        "key_markets": "عراق، عمان، کویت، امارات، روسیه"
    }
}

def enrich_entity(item: Dict[str, Any], country: str, query: str, mode: str) -> Dict[str, Any]:
    raw_name = item.get("name", "")
    clean_name = re.sub(r'\(.*?\)|\[.*?\]', '', raw_name).strip()
    if not clean_name:
        clean_name = raw_name
    
    encoded_co = urllib.parse.quote(clean_name)
    linkedin_company_url = f"https://www.linkedin.com/search/results/companies/?keywords={encoded_co}"
    
    if mode == "job":
        q_dork = f'site:linkedin.com/in "{clean_name}" ("HR" OR "Recruiter" OR "Talent Acquisition" OR "Hiring Manager" OR "Operations")'
        dm_title = "شکارچی مدیر استخدام و کارگزینی در لینکدین (HR & Recruiter)"
    else:
        q_dork = f'site:linkedin.com/in "{clean_name}" ("Procurement" OR "Purchasing" OR "Supply Chain" OR "Managing Director" OR "Owner")'
        dm_title = "شکارچی مدیر خرید و بازرگانی در لینکدین (Procurement)"
    
    linkedin_people_url = f"https://www.google.com/search?q={urllib.parse.quote(q_dork)}"
    
    skill_en = SKILL_TRANSLATIONS.get(query, query)
    country_en = country
    if "عراق" in country: country_en = "Iraq"
    elif "امارات" in country: country_en = "United Arab Emirates"
    elif "آلمان" in country: country_en = "Germany"
    elif "عمان" in country: country_en = "Oman"
    elif "ایران" in country: country_en = "Iran"
    elif "ترکیه" in country: country_en = "Turkey"
    elif "روسیه" in country: country_en = "Russia"
    linkedin_jobs_url = f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(skill_en)}&location={urllib.parse.quote(country_en)}"
    
    if "ایران" in country:
        registry_url = "https://ilenc.ssaa.ir/"
        registry_title = "استعلام شناسه ملی و روزنامه رسمی ایران"
    elif "عراق" in country:
        registry_url = "https://mot.gov.iq/"
        registry_title = "استعلام وزارت بازرگانی و شرکت‌های عراق"
    elif "امارات" in country:
        registry_url = "https://ner.economy.ae/"
        registry_title = "استعلام ثبت شرکت و DED امارات (NER)"
    elif "آلمان" in country:
        registry_url = "https://www.handelsregister.de/"
        registry_title = "استعلام ثبت تجاری آلمان (Handelsregister)"
    elif "عمان" in country:
        registry_url = "https://www.business.gov.om/"
        registry_title = "استعلام ثبت تجاری عمان (Invest Easy)"
    elif "ترکیه" in country:
        registry_url = "https://www.ticaretsicil.gov.tr/"
        registry_title = "استعلام روزنامه ثبت تجاری ترکیه (Sicil)"
    else:
        registry_url = f"https://www.google.com/search?q={urllib.parse.quote(f'{clean_name} company registration chamber of commerce')}"
        registry_title = f"استعلام اصالت و ثبت در اتاق بازرگانی {country}"
        
    enriched = dict(item)
    enriched["clean_name"] = clean_name
    enriched["linkedin_company_url"] = linkedin_company_url
    enriched["linkedin_people_url"] = linkedin_people_url
    enriched["linkedin_dm_title"] = dm_title
    enriched["linkedin_jobs_url"] = linkedin_jobs_url
    enriched["registry_url"] = registry_url
    enriched["registry_title"] = registry_title
    return enriched

class FreightCalcRequest(BaseModel):
    purchase_price_toman: float = 24000.0
    usd_to_toman: float = 94000.0
    packaging_toman: float = 3500.0
    transport_iran_toman: float = 40000000.0
    customs_toman: float = 35000000.0
    transit_usd: float = 1400.0
    usd_to_iqd: float = 1520.0
    cargo_weight_kg: float = 24000.0
    selling_price_usd_kg: float = 0.55

class InvoiceRequest(BaseModel):
    exporter_name: str = "بازرگانی بین‌المللی آریا"
    exporter_phone: str = "+989140000000"
    exporter_email: str = "export@domain.com"
    exporter_site: str = "https://export-hub.com"
    buyer_name: str = "Al-Rawi Wholesale Trading Co"
    buyer_country: str = "عراق"
    item_name: str = "سیب صادراتی سوپر لوکس (Red & Golden Apples - Grade A)"
    quantity_kg: float = 24000.0
    unit_price_usd: float = 0.55
    delivery_terms: str = "CPT Haj Omran Border (مرز تمرچین)"

@app.get("/api/search")
def search_entities(
    mode: str = Query("commodity", description="commodity or job"),
    country: str = Query("عراق"),
    query: str = Query("سیب"),
    live_search: bool = Query(False)
):
    country_clean = country.strip()
    query_clean = query.strip()
    
    if mode == "job":
        results = get_country_jobs_top_10(country_clean, query_clean)
        if live_search and len(results) < 5:
            extra = live_web_search_jobs(country_clean, query_clean)
            results.extend(extra)
            results = results[:10]
    else:
        results = get_country_top_10(country_clean, query_clean)
        if live_search and len(results) < 5:
            extra = live_web_search_contacts(country_clean, query_clean)
            results.extend(extra)
            results = results[:10]
            
    # Enrich with LinkedIn & Chamber intelligence
    enriched_results = [enrich_entity(r, country_clean, query_clean, mode) for r in results]
    
    # Check if HS info available for query
    matched_hs = None
    for k, v in HS_CODE_DATABASE.items():
        if k in query_clean or query_clean in k:
            matched_hs = v
            break

    return {
        "mode": mode,
        "country": country_clean,
        "query": query_clean,
        "count": len(enriched_results),
        "hs_info": matched_hs,
        "results": enriched_results
    }

@app.get("/api/hs-codes")
def get_hs_codes(product: Optional[str] = None):
    if product:
        for k, v in HS_CODE_DATABASE.items():
            if k in product or product in k:
                return {"product": k, "data": v}
    return {"all_products": HS_CODE_DATABASE}

@app.get("/api/dorks")
def get_osint_dorks(country: str = "عراق", product: str = "سیب"):
    c_en = country
    if "عراق" in country: c_en = "Iraq"
    elif "امارات" in country: c_en = "UAE Dubai"
    elif "آلمان" in country: c_en = "Germany"
    elif "عمان" in country: c_en = "Oman Muscat"
    elif "ایران" in country: c_en = "Iran"

    p_en = PRODUCT_TRANSLATIONS.get(product, product)
    
    dorks = [
        {
            "title": f"مدیران خرید، تأمین و بازرگانی در لینکدین برای {product} در {country}",
            "dork": f'site:linkedin.com/in ("{p_en}" OR "produce" OR "fruits") ("Procurement Manager" OR "Purchasing Director" OR "Head of Supply Chain") "{c_en}"',
            "purpose": "کشف مستقیم هویت، نام و پروفایل لینکدین تصمیم‌گیرندگان خرید کالا بدون واسطه‌ها"
        },
        {
            "title": f"مدیران استخدام و کارگزینی (HR & Recruiter) در لینکدین برای {country}",
            "dork": f'site:linkedin.com/in ("HR Manager" OR "Talent Acquisition" OR "Technical Recruiter") "{c_en}" "hiring" OR "jobs"',
            "purpose": "دستیابی به کارشناسان جذب نیرو و ویزای کار در کشور مقصد"
        },
        {
            "title": f"پرتال‌ها و دایرکتوری‌های رسمی واردکنندگان {product} در {country}",
            "dork": f'site:gov.* OR site:org.* OR inurl:directory "{p_en}" "importers" OR "wholesalers" "{c_en}" -b2b',
            "purpose": "کشف دایرکتوری‌های دولتی و اتاق‌های بازرگانی بدون واسطه‌ها"
        },
        {
            "title": f"فایل‌های اکسل و PDF مانیفست‌های گمرکی واردات در {country}",
            "dork": f'filetype:xlsx OR filetype:pdf "{p_en}" "importer" "{c_en}" "Bill of Lading" OR "Customs"',
            "purpose": "دستیابی به اسناد بارنامه‌های گمرکی واقعی خریداران پای باسکول"
        }
    ]
    return {"country": country, "product": product, "dorks": dorks}

@app.post("/api/calculate-freight")
def calculate_freight(req: FreightCalcRequest):
    cargo_kg = req.cargo_weight_kg
    purchase_toman = cargo_kg * req.purchase_price_toman
    packaging_toman = cargo_kg * req.packaging_toman
    domestic_transport = req.transport_iran_toman
    customs_toman = req.customs_toman
    
    total_cost_toman = purchase_toman + packaging_toman + domestic_transport + customs_toman
    total_cost_usd_ex_transit = total_cost_toman / req.usd_to_toman
    total_cost_usd = total_cost_usd_ex_transit + req.transit_usd
    
    gross_revenue_usd = cargo_kg * req.selling_price_usd_kg
    net_profit_usd = gross_revenue_usd - total_cost_usd
    net_profit_toman = net_profit_usd * req.usd_to_toman
    net_profit_iqd = (net_profit_usd / 100.0) * req.usd_to_iqd
    roi_percent = (net_profit_usd / total_cost_usd * 100.0) if total_cost_usd > 0 else 0.0

    # Multi-currency conversions
    net_profit_aed = net_profit_usd * 3.6725
    net_profit_eur = net_profit_usd * 0.92
    net_profit_try = net_profit_usd * 34.2
    net_profit_rub = net_profit_usd * 96.5

    return {
        "total_cost_usd": round(total_cost_usd, 2),
        "total_cost_toman": round(total_cost_toman, 0),
        "gross_revenue_usd": round(gross_revenue_usd, 2),
        "net_profit_usd": round(net_profit_usd, 2),
        "net_profit_toman": round(net_profit_toman, 0),
        "net_profit_iqd": round(net_profit_iqd, 0),
        "net_profit_aed": round(net_profit_aed, 0),
        "net_profit_eur": round(net_profit_eur, 0),
        "net_profit_try": round(net_profit_try, 0),
        "net_profit_rub": round(net_profit_rub, 0),
        "roi_percent": round(roi_percent, 1),
        "cost_per_kg_usd": round(total_cost_usd / cargo_kg, 3)
    }

@app.post("/api/proforma")
def generate_proforma(req: InvoiceRequest):
    pi_id = f"PI-{int(time.time())}"
    pi_date = time.strftime('%Y-%m-%d')
    total_amount = req.quantity_kg * req.unit_price_usd
    
    invoice_text = f"""======================================================================
                     PROFORMA INVOICE / فاتورة مبدئية
======================================================================
Invoice No:    {pi_id}
Date:          {pi_date}
Payment Terms: 100% Advance via Hawala / Exchange Office / Bank Transfer
Delivery Terms:{req.delivery_terms}
----------------------------------------------------------------------
EXPORTER / B2B SELLER:
Name:          {req.exporter_name}
Direct Phone:  {req.exporter_phone}
Official Email:{req.exporter_email}
Website:       {req.exporter_site}

BUYER / IMPORTER:
Company:       {req.buyer_name}
Country:       {req.buyer_country}
----------------------------------------------------------------------
COMMODITY SPECIFICATIONS:
Description:   {req.item_name}
Total Weight:  {req.quantity_kg:,.0f} KG (approx. 1 Full Truckload)
Unit Price:    ${req.unit_price_usd:.2f} USD / KG
----------------------------------------------------------------------
TOTAL AMOUNT:  ${total_amount:,.2f} USD
======================================================================
Authorized Signature & Official Stamp:
{req.exporter_name} - International Trade & Border Hub Division
"""
    return {
        "invoice_no": pi_id,
        "date": pi_date,
        "total_amount_usd": round(total_amount, 2),
        "invoice_text": invoice_text
    }

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
