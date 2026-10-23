from flask import Flask, render_template, request, redirect, url_for, send_file
from database import get_db_connection
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from io import BytesIO

app = Flask(__name__)


# ---------------- LOGIN ----------------

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor()

        query = "SELECT * FROM admin WHERE username=%s AND password=%s"
        cursor.execute(query, (username, password))

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user:
            return redirect(url_for("dashboard"))

        else:
            return render_template(
                "login.html",
                error="Invalid Username or Password"
            )

    return render_template("login.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT COUNT(*) AS total_customers FROM customers"
    )
    total_customers = cursor.fetchone()["total_customers"]

    cursor.execute(
        "SELECT IFNULL(SUM(amount), 0) AS total_udhaar FROM udhaar"
    )
    total_udhaar = cursor.fetchone()["total_udhaar"]

    cursor.execute(
        "SELECT IFNULL(SUM(amount_paid), 0) AS total_paid FROM payments"
    )
    total_paid = cursor.fetchone()["total_paid"]

    remaining = total_udhaar - total_paid

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        total_customers=total_customers,
        total_udhaar=total_udhaar,
        total_paid=total_paid,
        remaining=remaining
    )


# ---------------- CUSTOMERS ----------------

@app.route("/customers", methods=["GET", "POST"])
def customers():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        name = request.form["name"]
        mobile = request.form["mobile"]
        address = request.form["address"]

        query = """
        INSERT INTO customers(customer_name, mobile, address)
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            query,
            (name, mobile, address)
        )

        connection.commit()

    search = request.args.get("search")

    if search:

        cursor.execute("""
            SELECT *
            FROM customers
            WHERE customer_name LIKE %s
            OR mobile LIKE %s
            OR CAST(customer_id AS CHAR) LIKE %s
            ORDER BY customer_id ASC
        """, (
            f"%{search}%",
            f"%{search}%",
            f"%{search}%"
        ))

    else:

        cursor.execute("""
            SELECT *
            FROM customers
            ORDER BY customer_id ASC
        """)

    customers = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "customers.html",
        customers=customers
    )


# ---------------- CUSTOMER SEARCH DETAILS ----------------

@app.route("/customer_search")
def customer_search():

    return render_template("customer_search.html")


# ---------------- SEARCH CUSTOMERS ----------------

@app.route("/search_customers")
def search_customers():

    search = request.args.get("search", "").strip()

    if not search:

        return {
            "found": False,
            "customers": []
        }

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            customer_id,
            customer_name,
            mobile,
            address,
            registration_date
        FROM customers
        WHERE customer_name LIKE %s
           OR mobile LIKE %s
           OR CAST(customer_id AS CHAR) LIKE %s
        ORDER BY customer_name ASC
    """, (
        f"%{search}%",
        f"%{search}%",
        f"%{search}%"
    ))

    customers = cursor.fetchall()

    cursor.close()
    connection.close()

    return {
        "found": len(customers) > 0,
        "customers": customers
    }


# ---------------- GET CUSTOMER DETAILS ----------------

@app.route("/get_customer_details")
def get_customer_details():

    customer_id = request.args.get(
        "customer_id",
        ""
    ).strip()

    if not customer_id:

        return {
            "found": False
        }

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM customers
        WHERE customer_id = %s
    """, (customer_id,))

    customer = cursor.fetchone()

    if not customer:

        cursor.close()
        connection.close()

        return {
            "found": False
        }

    cursor.execute("""
        SELECT IFNULL(SUM(amount), 0) AS total_udhaar
        FROM udhaar
        WHERE customer_id = %s
    """, (customer_id,))

    total_udhaar = cursor.fetchone()["total_udhaar"]

    cursor.execute("""
        SELECT IFNULL(SUM(amount_paid), 0) AS total_paid
        FROM payments
        WHERE customer_id = %s
    """, (customer_id,))

    total_paid = cursor.fetchone()["total_paid"]

    cursor.execute("""
        SELECT
            product_name,
            quantity,
            amount,
            udhaar_date,
            due_date,
            notes
        FROM udhaar
        WHERE customer_id = %s
        ORDER BY udhaar_date DESC
    """, (customer_id,))

    udhaar_history = cursor.fetchall()

    cursor.execute("""
        SELECT
            amount_paid,
            payment_date,
            payment_method
        FROM payments
        WHERE customer_id = %s
        ORDER BY payment_date DESC
    """, (customer_id,))

    payment_history = cursor.fetchall()

    print("PAYMENT HISTORY:", payment_history)

    remaining = total_udhaar - total_paid

    cursor.close()
    connection.close()

    return {
        "found": True,
        "customer": customer,
        "total_udhaar": float(total_udhaar),
        "total_paid": float(total_paid),
        "remaining": float(remaining),
        "udhaar_history": udhaar_history,
        "payment_history": payment_history
    }


# ---------------- CUSTOMER PDF STATEMENT ----------------

@app.route("/customer_statement/<int:customer_id>")
def customer_statement(customer_id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM customers
        WHERE customer_id = %s
    """, (customer_id,))

    customer = cursor.fetchone()

    if not customer:

        cursor.close()
        connection.close()

        return "Customer not found", 404

    cursor.execute("""
        SELECT
            product_name,
            quantity,
            amount,
            udhaar_date,
            due_date,
            notes
        FROM udhaar
        WHERE customer_id = %s
        ORDER BY udhaar_date DESC
    """, (customer_id,))

    udhaar_history = cursor.fetchall()

    cursor.execute("""
        SELECT
            amount_paid,
            payment_date,
            payment_method
        FROM payments
        WHERE customer_id = %s
        ORDER BY payment_date DESC
    """, (customer_id,))

    payment_history = cursor.fetchall()

    total_udhaar = sum(
        float(u["amount"] or 0)
        for u in udhaar_history
    )

    total_paid = sum(
        float(p["amount_paid"] or 0)
        for p in payment_history
    )

    remaining = total_udhaar - total_paid

    cursor.close()
    connection.close()

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    title_style.alignment = TA_CENTER

    elements = []

    elements.append(
        Paragraph(
            "UDHAAR MANAGEMENT SYSTEM",
            title_style
        )
    )

    elements.append(
        Paragraph(
            "Customer Statement",
            styles["Heading2"]
        )
    )

    elements.append(Spacer(1, 15))

    customer_data = [
        ["Customer Name", customer["customer_name"]],
        ["Customer ID", str(customer["customer_id"])],
        ["Mobile", customer["mobile"] or "Not Available"],
        ["Address", customer["address"] or "Not Available"]
    ]

    customer_table = Table(
        customer_data,
        colWidths=[130, 350]
    )

    customer_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 8)
        ])
    )

    elements.append(customer_table)

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Financial Summary",
            styles["Heading2"]
        )
    )

    summary_data = [
        ["Total Udhaar", f"Rs. {total_udhaar:.2f}"],
        ["Total Paid", f"Rs. {total_paid:.2f}"],
        ["Remaining Balance", f"Rs. {remaining:.2f}"]
    ]

    summary_table = Table(
        summary_data,
        colWidths=[200, 280]
    )

    summary_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 8)
        ])
    )

    elements.append(summary_table)

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Udhaar History",
            styles["Heading2"]
        )
    )

    udhaar_data = [
        ["Product", "Quantity", "Amount", "Date"]
    ]

    for u in udhaar_history:

        udhaar_data.append([
            u["product_name"],
            str(u["quantity"] or 1),
            f"Rs. {float(u['amount'] or 0):.2f}",
            str(u["udhaar_date"])
        ])

    if len(udhaar_data) == 1:

        udhaar_data.append([
            "No records",
            "-",
            "-",
            "-"
        ])

    udhaar_table = Table(
        udhaar_data,
        colWidths=[180, 80, 100, 120]
    )

    udhaar_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 7)
        ])
    )

    elements.append(udhaar_table)

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Payment History",
            styles["Heading2"]
        )
    )

    payment_data = [
        ["Amount Paid", "Date", "Payment Method"]
    ]

    for p in payment_history:

        payment_data.append([
            f"Rs. {float(p['amount_paid'] or 0):.2f}",
            str(p["payment_date"]),
            p["payment_method"] or "Not Available"
        ])

    if len(payment_data) == 1:

        payment_data.append([
            "No records",
            "-",
            "-"
        ])

    payment_table = Table(
        payment_data,
        colWidths=[150, 150, 180]
    )

    payment_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 7)
        ])
    )

    elements.append(payment_table)

    elements.append(Spacer(1, 25))

    elements.append(
        Paragraph(
            f"<b>Remaining Balance: Rs. {remaining:.2f}</b>",
            styles["Heading2"]
        )
    )

    document.build(elements)

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"customer_statement_{customer_id}.pdf",
        mimetype="application/pdf"
    )


# ---------------- CUSTOMER DETAILS ----------------

@app.route("/customer/<int:id>")
def customer_details(id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM customers
        WHERE customer_id = %s
    """, (id,))

    customer = cursor.fetchone()

    if not customer:

        cursor.close()
        connection.close()

        return "Customer not found"

    cursor.execute("""
        SELECT IFNULL(SUM(amount), 0) AS total_udhaar
        FROM udhaar
        WHERE customer_id = %s
    """, (id,))

    total_udhaar = cursor.fetchone()["total_udhaar"]

    cursor.execute("""
        SELECT IFNULL(SUM(amount_paid), 0) AS total_paid
        FROM payments
        WHERE customer_id = %s
    """, (id,))

    total_paid = cursor.fetchone()["total_paid"]

    remaining = total_udhaar - total_paid

    cursor.execute("""
        SELECT
            udhaar_id,
            product_name,
            quantity,
            amount,
            udhaar_date,
            due_date,
            notes
        FROM udhaar
        WHERE customer_id = %s
        ORDER BY udhaar_id DESC
    """, (id,))

    udhaar_history = cursor.fetchall()

    cursor.execute("""
        SELECT
            payment_id,
            amount_paid,
            payment_date,
            payment_method
        FROM payments
        WHERE customer_id = %s
        ORDER BY payment_id DESC
    """, (id,))

    payment_history = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "customer_details.html",
        customer=customer,
        total_udhaar=total_udhaar,
        total_paid=total_paid,
        remaining=remaining,
        udhaar_history=udhaar_history,
        payment_history=payment_history
    )


# ---------------- DELETE CUSTOMER ----------------

@app.route("/delete_customer/<int:id>")
def delete_customer(id):

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            "DELETE FROM payments WHERE customer_id=%s",
            (id,)
        )

        cursor.execute(
            "DELETE FROM udhaar WHERE customer_id=%s",
            (id,)
        )

        cursor.execute(
            "DELETE FROM customers WHERE customer_id=%s",
            (id,)
        )

        connection.commit()

    except Exception as e:

        connection.rollback()

        return f"Error: {e}"

    finally:

        cursor.close()
        connection.close()

    return redirect(url_for("customers"))


# ---------------- EDIT CUSTOMER ----------------

@app.route("/edit_customer/<int:id>", methods=["GET", "POST"])
def edit_customer(id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        name = request.form["name"]
        mobile = request.form["mobile"]
        address = request.form["address"]

        cursor.execute("""
            UPDATE customers
            SET customer_name=%s,
                mobile=%s,
                address=%s
            WHERE customer_id=%s
        """, (
            name,
            mobile,
            address,
            id
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("customers"))

    cursor.execute(
        "SELECT * FROM customers WHERE customer_id=%s",
        (id,)
    )

    customer = cursor.fetchone()

    cursor.close()
    connection.close()

    return render_template(
        "edit_customer.html",
        customer=customer
    )


# ---------------- UDHAAR ----------------

@app.route("/udhaar", methods=["GET", "POST"])
def udhaar():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        customer_id = request.form["customer_id"]
        product_name = request.form["product_name"]

        # Quantity can contain numbers and characters
        # Example: 5kg, 2 boxes, 3 packets
        quantity = request.form["quantity"]

        amount = request.form["amount"]
        udhaar_date = request.form["udhaar_date"]
        due_date = request.form.get("due_date")
        notes = request.form.get("notes")

        query = """
            INSERT INTO udhaar
            (
                customer_id,
                product_name,
                quantity,
                amount,
                udhaar_date,
                due_date,
                notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (
                customer_id,
                product_name,
                quantity,
                amount,
                udhaar_date,
                due_date if due_date else None,
                notes
            )
        )

        connection.commit()

    cursor.execute("""
        SELECT
            customer_id,
            customer_name
        FROM customers
        ORDER BY customer_name ASC
    """)

    customers = cursor.fetchall()

    cursor.execute("""
        SELECT
            u.udhaar_id,
            u.customer_id,
            c.customer_name,
            u.product_name,
            u.quantity,
            u.amount,
            u.udhaar_date,
            u.due_date,
            u.notes
        FROM udhaar u
        JOIN customers c
        ON u.customer_id = c.customer_id
        ORDER BY c.customer_name ASC,
                 u.udhaar_date ASC
    """)

    udhaar = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "udhaar.html",
        customers=customers,
        udhaar=udhaar
    )


# ---------------- EDIT UDHAAR ----------------

@app.route("/edit_udhaar/<int:id>", methods=["GET", "POST"])
def edit_udhaar(id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        product_name = request.form["product_name"]

        # Quantity accepts numbers and characters
        # Example: 5kg, 2 boxes, 3 packets
        quantity = request.form["quantity"]

        amount = request.form["amount"]
        udhaar_date = request.form["udhaar_date"]
        due_date = request.form.get("due_date")
        notes = request.form.get("notes")

        query = """
            UPDATE udhaar
            SET product_name=%s,
                quantity=%s,
                amount=%s,
                udhaar_date=%s,
                due_date=%s,
                notes=%s
            WHERE udhaar_id=%s
        """

        cursor.execute(
            query,
            (
                product_name,
                quantity,
                amount,
                udhaar_date,
                due_date if due_date else None,
                notes,
                id
            )
        )

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("udhaar"))

    cursor.execute(
        "SELECT * FROM udhaar WHERE udhaar_id=%s",
        (id,)
    )

    udhaar = cursor.fetchone()

    cursor.close()
    connection.close()

    if not udhaar:
        return "Udhaar record not found", 404

    return render_template(
        "edit_udhaar.html",
        udhaar=udhaar
    )


# ---------------- DELETE UDHAAR ----------------

@app.route("/delete_udhaar/<int:id>")
def delete_udhaar(id):

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM udhaar WHERE udhaar_id = %s",
        (id,)
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("udhaar"))


# ---------------- PAYMENTS ----------------

@app.route("/payments", methods=["GET", "POST"])
def payments():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        customer_id = request.form["customer_id"]
        amount_paid = request.form["amount_paid"]
        payment_date = request.form["payment_date"]
        payment_method = request.form["payment_method"]

        query = """
            INSERT INTO payments
            (
                customer_id,
                amount_paid,
                payment_date,
                payment_method
            )
            VALUES (%s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (
                customer_id,
                amount_paid,
                payment_date,
                payment_method
            )
        )

        connection.commit()

    cursor.execute("""
        SELECT
            customer_id,
            customer_name
        FROM customers
        ORDER BY customer_name ASC
    """)

    customers = cursor.fetchall()

    cursor.execute("""
        SELECT
            p.payment_id,
            p.customer_id,
            c.customer_name,
            p.amount_paid,
            p.payment_date,
            p.payment_method
        FROM payments p
        JOIN customers c
        ON p.customer_id = c.customer_id
        ORDER BY p.payment_id DESC
    """)

    payments = cursor.fetchall()

    cursor.execute("""
        SELECT
            c.customer_id,
            c.customer_name,

            COALESCE(
                (
                    SELECT SUM(amount)
                    FROM udhaar
                    WHERE customer_id = c.customer_id
                ),
                0
            ) AS total_udhaar,

            COALESCE(
                (
                    SELECT SUM(amount_paid)
                    FROM payments
                    WHERE customer_id = c.customer_id
                ),
                0
            ) AS total_paid

        FROM customers c
        ORDER BY c.customer_name ASC
    """)

    payment_summary = cursor.fetchall()

    for customer in payment_summary:

        customer["remaining"] = (
            customer["total_udhaar"]
            - customer["total_paid"]
        )

    cursor.close()
    connection.close()

    return render_template(
        "payments.html",
        customers=customers,
        payments=payments,
        payment_summary=payment_summary
    )


# ---------------- PAYMENT RECEIPT PDF ----------------

@app.route("/payment_receipt/<int:payment_id>")
def payment_receipt(payment_id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            p.payment_id,
            p.customer_id,
            p.amount_paid,
            p.payment_date,
            p.payment_method,
            c.customer_name,
            c.mobile,
            c.address
        FROM payments p
        JOIN customers c
        ON p.customer_id = c.customer_id
        WHERE p.payment_id = %s
    """, (payment_id,))

    payment = cursor.fetchone()

    if not payment:

        cursor.close()
        connection.close()

        return "Payment not found", 404

    cursor.execute("""
        SELECT IFNULL(SUM(amount), 0) AS total_udhaar
        FROM udhaar
        WHERE customer_id = %s
    """, (payment["customer_id"],))

    total_udhaar = cursor.fetchone()["total_udhaar"]

    cursor.execute("""
        SELECT IFNULL(SUM(amount_paid), 0) AS total_paid
        FROM payments
        WHERE customer_id = %s
    """, (payment["customer_id"],))

    total_paid = cursor.fetchone()["total_paid"]

    remaining = total_udhaar - total_paid

    cursor.close()
    connection.close()

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    title_style.alignment = TA_CENTER

    elements = []

    elements.append(
        Paragraph(
            "UDHAAR MANAGEMENT SYSTEM",
            title_style
        )
    )

    elements.append(
        Paragraph(
            "PAYMENT RECEIPT",
            styles["Heading2"]
        )
    )

    elements.append(Spacer(1, 20))

    receipt_data = [
        ["Receipt No.", str(payment["payment_id"])],
        ["Payment Date", str(payment["payment_date"])],
    ]

    receipt_table = Table(
        receipt_data,
        colWidths=[150, 330]
    )

    receipt_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 8)
        ])
    )

    elements.append(receipt_table)

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Customer Information",
            styles["Heading2"]
        )
    )

    customer_data = [
        ["Customer Name", payment["customer_name"]],
        ["Customer ID", str(payment["customer_id"])],
        ["Mobile", payment["mobile"] or "Not Available"],
        ["Address", payment["address"] or "Not Available"]
    ]

    customer_table = Table(
        customer_data,
        colWidths=[150, 330]
    )

    customer_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 8)
        ])
    )

    elements.append(customer_table)

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Payment Details",
            styles["Heading2"]
        )
    )

    payment_data = [
        ["Amount Paid", f"Rs. {float(payment['amount_paid'] or 0):.2f}"],
        ["Payment Method", payment["payment_method"] or "Not Available"],
        ["Payment Date", str(payment["payment_date"])]
    ]

    payment_table = Table(
        payment_data,
        colWidths=[150, 330]
    )

    payment_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 8)
        ])
    )

    elements.append(payment_table)

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Balance Summary",
            styles["Heading2"]
        )
    )

    balance_data = [
        ["Total Udhaar", f"Rs. {float(total_udhaar):.2f}"],
        ["Total Paid", f"Rs. {float(total_paid):.2f}"],
        ["Remaining Balance", f"Rs. {float(remaining):.2f}"]
    ]

    balance_table = Table(
        balance_data,
        colWidths=[150, 330]
    )

    balance_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 8)
        ])
    )

    elements.append(balance_table)

    elements.append(Spacer(1, 30))

    elements.append(
        Paragraph(
            "Thank you for your payment.",
            styles["Heading3"]
        )
    )

    elements.append(Spacer(1, 15))

    elements.append(
        Paragraph(
            "This is a computer-generated receipt.",
            styles["Normal"]
        )
    )

    document.build(elements)

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"payment_receipt_{payment_id}.pdf",
        mimetype="application/pdf"
    )


# ---------------- EDIT PAYMENT ----------------

@app.route("/edit_payment/<int:id>", methods=["GET", "POST"])
def edit_payment(id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        amount_paid = request.form["amount_paid"]
        payment_date = request.form["payment_date"]
        payment_method = request.form["payment_method"]

        cursor.execute("""
            UPDATE payments
            SET amount_paid=%s,
                payment_date=%s,
                payment_method=%s
            WHERE payment_id=%s
        """, (
            amount_paid,
            payment_date,
            payment_method,
            id
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("payments"))

    cursor.execute("""
        SELECT *
        FROM payments
        WHERE payment_id=%s
    """, (id,))

    payment = cursor.fetchone()

    cursor.close()
    connection.close()

    if not payment:
        return "Payment not found"

    return render_template(
        "edit_payment.html",
        payment=payment
    )


# ---------------- DELETE PAYMENT ----------------

@app.route("/delete_payment/<int:id>")
def delete_payment(id):

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM payments WHERE payment_id=%s",
        (id,)
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("payments"))


# ---------------- REPORTS ----------------

@app.route("/reports")
def reports():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            c.customer_id,
            c.customer_name,

            IFNULL(
                SUM(u.amount),
                0
            ) AS total_udhaar,

            IFNULL(
                (
                    SELECT SUM(amount_paid)
                    FROM payments p
                    WHERE p.customer_id = c.customer_id
                ),
                0
            ) AS total_paid

        FROM customers c

        LEFT JOIN udhaar u
        ON c.customer_id = u.customer_id

        GROUP BY
            c.customer_id,
            c.customer_name

        ORDER BY c.customer_name ASC
    """

    cursor.execute(query)

    reports = cursor.fetchall()

    for report in reports:

        report["remaining"] = (
            report["total_udhaar"]
            - report["total_paid"]
        )

    cursor.close()
    connection.close()

    return render_template(
        "reports.html",
        reports=reports
    )


# ---------------- PENDING CUSTOMERS ----------------

@app.route("/pending_customers")
def pending_customers():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            c.customer_id,
            c.customer_name,
            c.mobile,

            COALESCE(
                (
                    SELECT SUM(amount)
                    FROM udhaar
                    WHERE customer_id = c.customer_id
                ),
                0
            ) AS total_udhaar,

            COALESCE(
                (
                    SELECT SUM(amount_paid)
                    FROM payments
                    WHERE customer_id = c.customer_id
                ),
                0
            ) AS total_paid

        FROM customers c

        ORDER BY c.customer_name ASC
    """

    cursor.execute(query)

    customers = cursor.fetchall()

    for customer in customers:

        customer["remaining"] = (
            customer["total_udhaar"]
            - customer["total_paid"]
        )

    pending = [
        customer
        for customer in customers
        if customer["remaining"] > 0
    ]

    cursor.close()
    connection.close()

    return render_template(
        "pending_customers.html",
        pending=pending
    )


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=True)

