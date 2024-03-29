import requests
from ..doctype.custom_exceptions import InvoiceAdditionError
# import frappe
# from .base import OBRAPIBase

# import requests
# class SalesInvoicePoster:

# 	def __init__(self, token:str):
# 		obr_base = OBRAPIBase()
# 		self.BASE_ADD_INVOICE_API_URL = obr_base.get_api_from_ebims_settings("add_invoice")
# 		self.token = token

# 	def _retry_request(self, data):
# 		response = None
# 		try:
# 			response = requests.post(self.BASE_ADD_INVOICE_API_URL, json=data, headers=self._get_headers())
# 			response.raise_for_status()
			
# 			if not response.json().get("success"):
# 				frappe.log_error(f"Unexpected API response format: {response.text}", reference_doctype="Sales Invoice", reference_name=data.get("invoice_number"))
# 				raise InvoiceAdditionError(f"Unexpected API response format: {response.text}")
			
# 			return response.json()
# 		except requests.exceptions.RequestException as e:
# 			error_message = f"Error during API request: {str(e)}"
# 			frappe.log_error(error_message, f"SalesInvoicePoster Request Error{str(e)}",reference_doctype="Sales Invoice", reference_name=data.get("invoice_number"))
# 			frappe.log_error(f"Response content: {response.text}")
# 			return response.json()
  
# 	def _send_request(self, data):
# 		return self._retry_request(data)

# 	def _handle_response(self, response):
# 		if response.get("success"):
# 			self.update_sales_invoice(response)
# 			return response
# 		else:
# 			raise InvoiceAdditionError(response["msg"])

# 	def _get_headers(self)->dict:
# 		return {
# 			"Content-Type": "application/json",
# 			"Authorization": f"Bearer {self.token}"
# 		}

# 	def post_invoice(self, invoice_data)->dict:
# 		response = self._send_request(invoice_data)
# 		return self._handle_response(response)

 
# 	'''Update Sales Invoice with the electronic signature 
# 		and the registered number and date of the invoice.'''
		
# 	def update_sales_invoice(self, response):
# 		try:
# 			invoice_number = response.get("result", {}).get("invoice_number")
# 			electronic_signature = response.get("electronic_signature")
# 			invoice_registered_no = response.get("result", {}).get("invoice_registered_number")
# 			invoice_registered_date = response.get("result", {}).get("invoice_registered_date")
			
# 			# Check the doctype directly
# 			invoice_type = "POS Invoice" if frappe.db.exists("POS Invoice", invoice_number) else "Sales Invoice"
# 			sales_invoice = frappe.get_doc(invoice_type, invoice_number)
    
# 			# Update Sales Invoice fields
# 			sales_invoice.custom_einvoice_signatures = electronic_signature
# 			sales_invoice.custom_invoice_registered_no = invoice_registered_no
# 			sales_invoice.custom_invoice_registered_date = invoice_registered_date
# 			sales_invoice.custom_submitted_to_obr=1

# 			# Save the Sales Invoice
# 			sales_invoice.save()
# 			frappe.db.commit()
# 			frappe.publish_realtime("msgprint", f"Sales Invoice {invoice_number} sent successfully", user=frappe.session.user)
# 		except Exception as e:
# 			frappe.db.rollback()
# 			frappe.log_error(f"Error updating Sales Invoice {invoice_number}: {str(e)}")

import json
import frappe
from frappe.integrations.utils import make_post_request, make_get_request, create_request_log
from .base import OBRAPIBase

class SalesInvoicePoster:

    def __init__(self, token: str):
        obr_base = OBRAPIBase()
        self.BASE_ADD_INVOICE_API_URL = obr_base.get_api_from_ebims_settings("add_invoice")
        self.token = token
    def _update_integration_request(self, response, invoice_data):
        success = response.get("success")
        if success:
            integration_req = self.check_if_integration_request_exist(invoice_data)
            if integration_req:
                try:
                    doc = frappe.get_doc("Integration Request", invoice_data.get('invoice_number'))
                    doc.status = "Completed"
                    doc.output = response.get("msg", "")
                    doc.error = ""
                    doc.save()
                except Exception as e:
                    frappe.publish_realtime("msgprint", f"Error while saving Integration Request: {str(e)}", user=frappe.session.user)
                    frappe.log_error(f"Error saving Integration Request: {str(e)}")

    def _handle_response(self, response, invoice_data):
        success = response.get("success")
        if success:
            self.update_sales_invoice(response)
            self._update_integration_request(response, invoice_data)
        else:
            create_request_log(invoice_data,
                integration_type=None,
                service_name="eBMS Invoice",
                name=invoice_data.get("invoice_number"),
                error="",
                url=self.BASE_ADD_INVOICE_API_URL,
                request_headers=self._get_headers(),
                output=response,
                reference_doctype="Sales Invoice",
                reference_docname=invoice_data.get("invoice_number"),
                status="Completed"
            )
        return response

    
    def check_if_integration_request_exist(self, invoice_data):
        integration_request = frappe.db.exists("Integration Request", {
            "reference_doctype": "Sales Invoice",
            "reference_docname": invoice_data.get("invoice_number")
        })
        if integration_request:
            return True
        else:
            return False

    def _get_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }


    def post_invoice(self, invoice_data) -> dict:
        try:
            #make_post_request doesn't seem to work well here
            #It doesn't give me the freedom to handle the response
            response = requests.post(
                self.BASE_ADD_INVOICE_API_URL,
                json=invoice_data,
                headers=self._get_headers()
            )
            response_data = json.loads(response.text)
            msg=response_data.get("msg")
            success=response_data.get("success")
            doc=frappe.get_doc("Sales Invoice", invoice_data.get("invoice_number"))
            if success==False:
                frappe.publish_realtime("msgprint", f"Error while sending your invoice \n: <div style='color:red;'>{msg}</div>", user=doc.owner)
                create_request_log(invoice_data,
                                        integration_type=None,
                                        service_name="eBMS Invoice",
                                        error=msg,
                                        name=invoice_data.get("invoice_number"),
                                        request_headers=self._get_headers(),
                                        output=response_data,
                                        reference_doctype="Sales Invoice",
                                        reference_docname=invoice_data.get("invoice_number"),
                                        status="Failed",
                                        url=self.BASE_ADD_INVOICE_API_URL
                                        )
            elif success==True:
                return self._handle_response(response_data, invoice_data)
        except Exception as e:
            frappe.log_error(f"Error during API request: {str(e)}")
        

    def update_sales_invoice(self, response):
        try:
            invoice_number = response.get("result", {}).get("invoice_number")
            electronic_signature = response.get("electronic_signature")
            invoice_registered_no = response.get("result", {}).get("invoice_registered_number")
            invoice_registered_date = response.get("result", {}).get("invoice_registered_date")

            # Check the doctype directly
            invoice_type = "POS Invoice" if frappe.db.exists("POS Invoice", invoice_number) else "Sales Invoice"
            sales_invoice = frappe.get_doc(invoice_type, invoice_number)

            # Update Sales Invoice fields
            sales_invoice.custom_einvoice_signatures = electronic_signature
            sales_invoice.custom_invoice_registered_no = invoice_registered_no
            sales_invoice.custom_invoice_registered_date = invoice_registered_date
            sales_invoice.custom_submitted_to_obr = 1

            # Save the Sales Invoice
            sales_invoice.save()
            frappe.db.commit()
            frappe.publish_realtime("msgprint", f"Sales Invoice {invoice_number} sent successfully", user=frappe.session.user)
        except Exception as e:
            # Log the error
            frappe.log_error(f"Error updating Sales Invoice {invoice_number}: {str(e)}")

            # Create Integration Request document for failure
            self.create_integration_request(response, False, str(e))
