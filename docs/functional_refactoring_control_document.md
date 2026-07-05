# Functional Refactoring Control Document for Python Codebases

## Document Purpose

This control document defines how an existing Python codebase should be refactored toward a more functional structure.

The aim is **not** to make Python look like Scala, Haskell, F#, or any other functional-first language. The aim is to apply functional programming principles in a Pythonic way so that the codebase becomes easier to reason about, easier to test, easier to modify, and safer for both humans and AI coding tools to work with.

The intended target is a codebase where:

- business logic is concentrated in pure or mostly pure functions;
- side effects are explicit and pushed toward the edges of the system;
- data transformation pipelines are easy to follow;
- mutable shared state is reduced;
- dependencies are passed explicitly rather than accessed globally;
- modules have clear responsibilities;
- tests can exercise core behaviour without requiring databases, APIs, filesystems, clocks, random generators, or global configuration;
- AI tools can perform refactors in smaller, safer, more reviewable steps.

This document should be treated as a project-level standard for AI-assisted refactoring.

---

## 1. Core Philosophy

### 1.1 Functional structure, not functional theatre

Functional refactoring should improve the codebase in substance, not merely add functional-looking syntax.

Good functional Python should look clear, named, explicit, and idiomatic.

```python
def active_users(users: Iterable[User]) -> list[User]:
    return [user for user in users if user.is_active]


def email_addresses(users: Iterable[User]) -> list[str]:
    return [user.email for user in users]


def active_user_emails(users: Iterable[User]) -> list[str]:
    return email_addresses(active_users(users))
```

Avoid replacing readable Python with dense functional theatre.

```python
from functools import reduce

active_user_emails = lambda users: list(
    map(
        lambda u: u.email,
        filter(lambda u: u.is_active, users),
    )
)
```

The refactoring standard is:

> Use functional ideas to make Python clearer, not to make Python look like another language.

---

### 1.2 Functional core, imperative shell

The preferred architecture is:

```text
External world
    ↓
Imperative shell
    ↓
Pure or mostly pure functional core
    ↓
Imperative shell
    ↓
External world
```

The **functional core** contains deterministic business logic.

The **imperative shell** handles interaction with external systems.

Examples of imperative shell responsibilities:

- HTTP request and response handling;
- command-line argument parsing;
- database reads and writes;
- filesystem reads and writes;
- network calls;
- queues and message brokers;
- caches;
- logging;
- metrics;
- environment variables;
- current time;
- random number generation;
- framework-specific objects;
- dependency construction.

The core should answer questions of the form:

```text
Given this input data, what should the system decide?
```

The shell should perform actions of the form:

```text
Read this request.
Fetch this data.
Call the pure decision function.
Persist the result.
Return or publish the response.
```

The core decides. The shell does.

---

### 1.3 Make data flow explicit

Refactored code should make the movement of data through the system visible.

Prefer this:

```python
def build_invoice_summary(invoice: Invoice) -> InvoiceSummary:
    billable_lines = select_billable_lines(invoice.lines)
    line_totals = calculate_line_totals(billable_lines)
    subtotal = sum_line_totals(line_totals)
    tax = calculate_tax(subtotal, invoice.tax_region)
    total = subtotal + tax

    return InvoiceSummary(
        invoice_id=invoice.id,
        subtotal=subtotal,
        tax=tax,
        total=total,
    )
```

Avoid this:

```python
def build_invoice_summary(invoice: Invoice) -> InvoiceSummary:
    invoice.calculate()
    invoice.apply_tax()
    invoice.normalize()
    return invoice.summary
```

The second version hides behaviour inside mutation. The first version exposes the pipeline.

---

## 2. Definitions

### 2.1 Pure function

A pure function:

1. depends only on its explicit arguments;
2. returns a value;
3. does not mutate its inputs;
4. does not read or write external state;
5. does not perform I/O;
6. returns the same result for the same inputs.

Example:

```python
def calculate_discounted_total(
    total: Decimal,
    discount_rate: Decimal,
) -> Decimal:
    return total * (Decimal("1") - discount_rate)
```

Non-pure version:

```python
def calculate_discounted_total(total: Decimal) -> Decimal:
    discount_rate = Decimal(os.environ["DISCOUNT_RATE"])
    logger.info("Calculating discount")
    return total * (Decimal("1") - discount_rate)
```

The second function reads global configuration and logs internally. Refactoring should move those behaviours outward.

---

### 2.2 Side effect

A side effect is any interaction with state outside the local return value of the function.

Common side effects include:

- database reads;
- database writes;
- network calls;
- filesystem access;
- printing;
- logging;
- metrics emission;
- mutating arguments;
- updating globals;
- reading environment variables;
- reading current time;
- generating random values;
- changing caches;
- sending messages;
- calling framework-specific APIs.

Side effects are not forbidden. They should be isolated, explicit, and easy to locate.

---

### 2.3 Referential transparency

A piece of code is referentially transparent when it can be replaced by its value without changing program behaviour.

```python
tax = calculate_tax(subtotal, region)
```

If `calculate_tax(subtotal, region)` is pure, then the expression can be reasoned about as a value.

This property makes code easier to test, cache, parallelize, and refactor.

---

### 2.4 Immutable data

Immutable data is data that is not changed after construction.

In Python, prefer immutable domain models where practical.

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str
```

Avoid domain logic that relies on changing objects in place.

```python
class Money:
    def apply_discount(self, rate: Decimal) -> None:
        self.amount = self.amount * (Decimal("1") - rate)
```

Python cannot enforce immutability perfectly everywhere, but refactoring should move the codebase toward stable values and explicit replacement.

---

## 3. Refactoring Objectives

AI-assisted functional refactoring should optimize for these objectives, in this order:

1. Preserve existing observable behaviour.
2. Improve testability.
3. Separate pure business logic from side effects.
4. Make dependencies explicit.
5. Reduce mutation and shared state.
6. Clarify data flow.
7. Improve type clarity.
8. Simplify module boundaries.
9. Avoid clever abstractions unless they clearly reduce complexity.

Do not prioritize stylistic purity over maintainability.

---

## 4. Non-Goals

The refactoring process should not attempt to:

- eliminate all classes;
- eliminate all loops;
- eliminate all exceptions;
- replace all code with `map`, `filter`, `reduce`, or lambdas;
- introduce monads or category-theory terminology unless the codebase already uses them;
- rewrite the whole codebase in one pass;
- convert Python into Scala-style syntax;
- create abstract frameworks before concrete duplication exists;
- move every function into tiny files;
- hide straightforward code behind over-generalized combinators.

Functional refactoring should make the code more boring, more predictable, and easier to test.

---

## 5. Target Architecture

### 5.1 Preferred high-level structure

For a moderately complex Python application, the target architecture should separate these concerns:

```text
project/
    domain/
        models.py
        calculations.py
        policies.py
        validation.py

    application/
        use_cases.py
        commands.py
        queries.py
        workflows.py

    infrastructure/
        repositories.py
        clients.py
        filesystem.py
        clock.py
        config.py

    interfaces/
        http/
            routes.py
            serializers.py
        cli/
            commands.py
        workers/
            tasks.py

    tests/
        domain/
        application/
        infrastructure/
        interfaces/
```

The exact names may differ. The important separation is:

```text
Domain          = pure business logic and domain data
Application     = use-case orchestration
Infrastructure  = side-effecting adapters
Interfaces      = HTTP, CLI, workers, framework boundaries
```

---

### 5.2 Domain layer

The domain layer should contain the most functional code.

It should include:

- pure calculations;
- validation rules;
- eligibility rules;
- pricing logic;
- transformation functions;
- immutable domain data;
- domain-specific result types;
- policy functions.

It should avoid:

- database calls;
- HTTP calls;
- framework imports;
- logging;
- reading environment variables;
- accessing global configuration;
- sending messages;
- mutating external state.

Example:

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class OrderLine:
    sku: str
    unit_price: Decimal
    quantity: int


@dataclass(frozen=True)
class Order:
    id: str
    lines: tuple[OrderLine, ...]
    customer_region: str


def line_total(line: OrderLine) -> Decimal:
    return line.unit_price * line.quantity


def order_subtotal(order: Order) -> Decimal:
    return sum(line_total(line) for line in order.lines)


def qualifies_for_free_shipping(order: Order) -> bool:
    return order_subtotal(order) >= Decimal("50.00")
```

---

### 5.3 Application layer

The application layer coordinates use cases.

It may call infrastructure, but it should keep orchestration explicit and thin.

Example:

```python
def submit_order(
    command: SubmitOrderCommand,
    order_repository: OrderRepository,
    payment_client: PaymentClient,
    clock: Clock,
) -> SubmitOrderResult:
    order = order_repository.get(command.order_id)

    decision = decide_order_submission(
        order=order,
        payment_details=command.payment_details,
        submitted_at=clock.now(),
    )

    if isinstance(decision, OrderSubmissionRejected):
        return SubmitOrderResult.rejected(decision.reasons)

    payment_result = payment_client.charge(decision.payment_request)

    if not payment_result.success:
        return SubmitOrderResult.payment_failed(payment_result.reason)

    order_repository.save(decision.updated_order)

    return SubmitOrderResult.accepted(decision.confirmation)
```

The application layer may be impure, but it should delegate business decisions to pure functions.

---

### 5.4 Infrastructure layer

The infrastructure layer contains side effects.

Examples:

```python
class SqlOrderRepository:
    def get(self, order_id: str) -> Order:
        ...

    def save(self, order: Order) -> None:
        ...


class StripePaymentClient:
    def charge(self, request: PaymentRequest) -> PaymentResult:
        ...
```

Infrastructure classes should not contain business rules except translation logic required to interact with external systems.

---

### 5.5 Interface layer

The interface layer adapts the outside world to application use cases.

For HTTP code, this means:

```python
@router.post("/orders/{order_id}/submit")
def submit_order_route(order_id: str, request: SubmitOrderRequest):
    command = SubmitOrderCommand(
        order_id=order_id,
        payment_details=request.payment_details,
    )

    result = submit_order(
        command=command,
        order_repository=container.order_repository,
        payment_client=container.payment_client,
        clock=container.clock,
    )

    return to_http_response(result)
```

The route should not contain core business logic.

---

## 6. Core Refactoring Rules

### Rule 1: Extract pure decision logic from impure functions

When a function performs both business logic and side effects, split it.

Before:

```python
def process_refund(refund_id: str) -> None:
    refund = db.get_refund(refund_id)
    order = db.get_order(refund.order_id)

    if order.status != "paid":
        logger.warning("Cannot refund unpaid order")
        db.update_refund_status(refund_id, "rejected")
        return

    if refund.amount > order.total:
        logger.warning("Refund too large")
        db.update_refund_status(refund_id, "rejected")
        return

    payment_gateway.refund(order.payment_id, refund.amount)
    db.update_refund_status(refund_id, "processed")
```

After:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RefundDecision:
    accepted: bool
    reason: str | None = None


def decide_refund(refund: Refund, order: Order) -> RefundDecision:
    if order.status != "paid":
        return RefundDecision(False, "Cannot refund unpaid order")

    if refund.amount > order.total:
        return RefundDecision(False, "Refund amount exceeds order total")

    return RefundDecision(True)
```

Then keep side effects in the shell:

```python
def process_refund(
    refund_id: str,
    refund_repository: RefundRepository,
    order_repository: OrderRepository,
    payment_gateway: PaymentGateway,
    logger: Logger,
) -> None:
    refund = refund_repository.get(refund_id)
    order = order_repository.get(refund.order_id)

    decision = decide_refund(refund, order)

    if not decision.accepted:
        logger.warning(decision.reason)
        refund_repository.update_status(refund_id, "rejected")
        return

    payment_gateway.refund(order.payment_id, refund.amount)
    refund_repository.update_status(refund_id, "processed")
```

---

### Rule 2: Replace hidden dependencies with explicit arguments

Avoid functions that reach into global state.

Before:

```python
def calculate_price(cart: Cart) -> Decimal:
    tax_rate = settings.TAX_RATE
    discount = discount_service.current_discount()
    return cart.subtotal * (Decimal("1") + tax_rate) - discount
```

After:

```python
def calculate_price(
    cart: Cart,
    tax_rate: Decimal,
    discount: Decimal,
) -> Decimal:
    return cart.subtotal * (Decimal("1") + tax_rate) - discount
```

The caller is responsible for acquiring external values:

```python
def price_cart(
    cart: Cart,
    settings: Settings,
    discount_service: DiscountService,
) -> Decimal:
    return calculate_price(
        cart=cart,
        tax_rate=settings.tax_rate,
        discount=discount_service.current_discount(),
    )
```

Pure logic should receive values, not fetch them.

---

### Rule 3: Do not mutate inputs unless mutation is explicit

Before:

```python
def normalize_user(user: User) -> User:
    user.email = user.email.strip().lower()
    user.name = user.name.strip()
    return user
```

After:

```python
from dataclasses import replace


def normalize_user(user: User) -> User:
    return replace(
        user,
        email=user.email.strip().lower(),
        name=user.name.strip(),
    )
```

For dictionaries:

```python
def with_normalized_email(user: dict[str, Any]) -> dict[str, Any]:
    return {
        **user,
        "email": user["email"].strip().lower(),
    }
```

Mutation is allowed when:

- performance requires it and the code is localized;
- the function name makes mutation explicit;
- the mutation is confined to infrastructure or framework integration;
- tests cover the mutation boundary.

Examples of explicit mutation names:

```text
update_user_in_place
populate_cache
write_rows
append_audit_event
mutate_buffer
```

---

### Rule 4: Prefer expressions that produce values

Functional refactoring should move code away from procedural state accumulation when a direct value expression is clearer.

Before:

```python
eligible = []
for customer in customers:
    if customer.active and customer.balance <= 0:
        eligible.append(customer)
```

After:

```python
eligible = [
    customer
    for customer in customers
    if customer.active and customer.balance <= 0
]
```

Before:

```python
has_failed_payment = False
for payment in payments:
    if payment.status == "failed":
        has_failed_payment = True
        break
```

After:

```python
has_failed_payment = any(payment.status == "failed" for payment in payments)
```

Before:

```python
all_complete = True
for task in tasks:
    if not task.complete:
        all_complete = False
        break
```

After:

```python
all_complete = all(task.complete for task in tasks)
```

Use Python's built-ins where they express intent clearly:

```text
sum
any
all
min
max
sorted
next
enumerate
zip
```

---

### Rule 5: Name intermediate transformations when they carry meaning

Do not collapse meaningful steps into one dense expression.

Acceptable:

```python
def calculate_monthly_revenue(invoices: Iterable[Invoice]) -> Decimal:
    paid_invoices = [invoice for invoice in invoices if invoice.status == "paid"]
    invoice_totals = [invoice.total for invoice in paid_invoices]
    return sum(invoice_totals)
```

Often better for larger logic:

```python
def paid_invoices(invoices: Iterable[Invoice]) -> list[Invoice]:
    return [invoice for invoice in invoices if invoice.status == "paid"]


def invoice_totals(invoices: Iterable[Invoice]) -> list[Decimal]:
    return [invoice.total for invoice in invoices]


def calculate_monthly_revenue(invoices: Iterable[Invoice]) -> Decimal:
    return sum(invoice_totals(paid_invoices(invoices)))
```

Avoid dense expressions that hide business rules:

```python
def calculate_monthly_revenue(invoices):
    return sum(
        i.total
        for i in invoices
        if i.status == "paid"
        and i.total > 0
        and not i.voided
        and i.region != "internal"
    )
```

This should be decomposed into named predicates.

---

### Rule 6: Prefer domain data objects over loose dictionaries

Dictionaries are acceptable at boundaries, especially when parsing JSON. Inside the domain layer, prefer typed data.

Before:

```python
def can_ship(order: dict) -> bool:
    return (
        order["status"] == "paid"
        and order["address"]["country"] in SUPPORTED_COUNTRIES
    )
```

After:

```python
@dataclass(frozen=True)
class Address:
    country: str
    postcode: str


@dataclass(frozen=True)
class Order:
    id: str
    status: str
    address: Address


def can_ship(order: Order, supported_countries: set[str]) -> bool:
    return (
        order.status == "paid"
        and order.address.country in supported_countries
    )
```

Boundary conversion should happen once:

```python
def parse_order(payload: dict[str, Any]) -> Order:
    return Order(
        id=payload["id"],
        status=payload["status"],
        address=Address(
            country=payload["address"]["country"],
            postcode=payload["address"]["postcode"],
        ),
    )
```

Avoid passing raw, unvalidated dictionaries deep into the system.

---

### Rule 7: Use immutable containers for domain models where practical

Prefer:

```python
@dataclass(frozen=True)
class Basket:
    items: tuple[BasketItem, ...]
```

Instead of:

```python
@dataclass
class Basket:
    items: list[BasketItem]
```

Guidance:

- If ordering and duplicates matter, use `tuple`.
- If uniqueness matters, use `frozenset`.
- If lookup matters, use a mapping but avoid mutating it after construction.

This reduces accidental cross-function mutation.

---

### Rule 8: Separate validation from execution

Avoid functions that validate, mutate, persist, and notify in one body.

Before:

```python
def activate_account(account_id: str):
    account = db.accounts.get(account_id)

    if account.status == "closed":
        raise ValueError("Closed accounts cannot be activated")

    account.status = "active"
    db.accounts.save(account)
    email.send_activation_notice(account.email)
```

After:

```python
@dataclass(frozen=True)
class ActivationAccepted:
    account: Account


@dataclass(frozen=True)
class ActivationRejected:
    reason: str


ActivationDecision = ActivationAccepted | ActivationRejected


def decide_account_activation(account: Account) -> ActivationDecision:
    if account.status == "closed":
        return ActivationRejected("Closed accounts cannot be activated")

    return ActivationAccepted(replace(account, status="active"))
```

Then:

```python
def activate_account(
    account_id: str,
    account_repository: AccountRepository,
    email_sender: EmailSender,
) -> ActivationDecision:
    account = account_repository.get(account_id)
    decision = decide_account_activation(account)

    if isinstance(decision, ActivationRejected):
        return decision

    account_repository.save(decision.account)
    email_sender.send_activation_notice(decision.account.email)

    return decision
```

The decision is pure. The execution is impure.

---

### Rule 9: Make time, randomness, and configuration explicit

These are common hidden impurities.

Before:

```python
def create_session(user_id: str) -> Session:
    return Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=2),
    )
```

After:

```python
def create_session(
    user_id: str,
    session_id: str,
    created_at: datetime,
    lifetime: timedelta,
) -> Session:
    return Session(
        id=session_id,
        user_id=user_id,
        created_at=created_at,
        expires_at=created_at + lifetime,
    )
```

Shell:

```python
def create_user_session(
    user_id: str,
    clock: Clock,
    id_generator: IdGenerator,
) -> Session:
    return create_session(
        user_id=user_id,
        session_id=id_generator.new_id(),
        created_at=clock.now(),
        lifetime=timedelta(hours=2),
    )
```

This makes testing much easier.

---

### Rule 10: Keep logging out of pure logic

Before:

```python
def calculate_risk_score(user: User) -> int:
    logger.info("Calculating risk score for user %s", user.id)

    score = 0

    if user.failed_logins > 3:
        logger.warning("High failed login count")
        score += 10

    if user.country in HIGH_RISK_COUNTRIES:
        logger.warning("High risk country")
        score += 20

    return score
```

After:

```python
@dataclass(frozen=True)
class RiskAssessment:
    score: int
    reasons: tuple[str, ...]


def calculate_risk_score(
    user: User,
    high_risk_countries: set[str],
) -> RiskAssessment:
    reasons: list[str] = []
    score = 0

    if user.failed_logins > 3:
        score += 10
        reasons.append("High failed login count")

    if user.country in high_risk_countries:
        score += 20
        reasons.append("High risk country")

    return RiskAssessment(score=score, reasons=tuple(reasons))
```

Shell:

```python
assessment = calculate_risk_score(user, high_risk_countries)

for reason in assessment.reasons:
    logger.warning(reason)
```

The pure function returns information. The shell decides what to log.

---

## 7. Pattern Catalogue

### Pattern 1: Functional core, imperative shell

Use this whenever a function mixes business rules with I/O.

Target shape:

```python
def decide_something(input_data: DomainInput) -> DomainDecision:
    ...


def perform_something(command: Command, deps: Dependencies) -> Result:
    data = deps.repository.get(command.id)
    decision = decide_something(data)

    if decision.requires_external_action:
        deps.client.call(decision.request)

    deps.repository.save(decision.updated_data)

    return to_result(decision)
```

Use for:

- payment flows;
- account changes;
- order processing;
- notification workflows;
- document generation;
- import/export jobs;
- scheduled tasks;
- queue workers.

---

### Pattern 2: Parse, validate, transform, execute

This is useful at system boundaries.

```text
Raw input
    ↓
Parse into typed data
    ↓
Validate
    ↓
Transform / decide
    ↓
Execute side effects
    ↓
Return response
```

Example:

```python
def handle_create_user_request(payload: dict[str, Any]) -> HttpResponse:
    parse_result = parse_create_user_payload(payload)

    if isinstance(parse_result, InvalidPayload):
        return bad_request(parse_result.errors)

    validation_result = validate_create_user(parse_result.command)

    if isinstance(validation_result, InvalidCommand):
        return unprocessable_entity(validation_result.errors)

    result = create_user(parse_result.command)

    return created(to_response_body(result))
```

The parser and validator can usually be pure.

---

### Pattern 3: Return decisions, not side effects

Instead of making a function perform actions directly, have it return a decision describing what should happen.

Before:

```python
def check_inventory(order):
    if not inventory.has_stock(order.sku, order.quantity):
        email.send_out_of_stock(order.customer_email)
        order.reject()
```

After:

```python
@dataclass(frozen=True)
class Notification:
    recipient: str
    template: str


@dataclass(frozen=True)
class InventoryDecision:
    accepted: bool
    notifications: tuple[Notification, ...]


def decide_inventory(order: Order, stock: StockLevel) -> InventoryDecision:
    if stock.available < order.quantity:
        return InventoryDecision(
            accepted=False,
            notifications=(
                Notification(
                    recipient=order.customer_email,
                    template="out_of_stock",
                ),
            ),
        )

    return InventoryDecision(accepted=True, notifications=())
```

The shell sends notifications.

---

### Pattern 4: Data transformation pipeline

Use named transformations when processing collections.

```python
def eligible_orders(orders: Iterable[Order]) -> list[Order]:
    return [
        order for order in orders
        if order.status == "paid" and not order.cancelled
    ]


def orders_by_customer(orders: Iterable[Order]) -> dict[str, list[Order]]:
    grouped: dict[str, list[Order]] = {}

    for order in orders:
        grouped.setdefault(order.customer_id, []).append(order)

    return grouped


def customer_summaries(orders: Iterable[Order]) -> list[CustomerOrderSummary]:
    eligible = eligible_orders(orders)
    grouped = orders_by_customer(eligible)

    return [
        CustomerOrderSummary(
            customer_id=customer_id,
            order_count=len(customer_orders),
            total=sum(order.total for order in customer_orders),
        )
        for customer_id, customer_orders in grouped.items()
    ]
```

A loop is acceptable when it is clearer than a forced functional expression.

---

### Pattern 5: Explicit dependency bundle

When a use case has several infrastructure dependencies, pass them explicitly.

For small functions:

```python
def cancel_order(
    order_id: str,
    order_repository: OrderRepository,
    payment_client: PaymentClient,
    email_sender: EmailSender,
) -> CancelOrderResult:
    ...
```

For larger use cases:

```python
@dataclass(frozen=True)
class CancelOrderDependencies:
    order_repository: OrderRepository
    payment_client: PaymentClient
    email_sender: EmailSender
    clock: Clock


def cancel_order(
    command: CancelOrderCommand,
    deps: CancelOrderDependencies,
) -> CancelOrderResult:
    ...
```

Avoid accessing dependencies from global containers inside the domain layer.

---

### Pattern 6: Replace mutation with replacement

For dataclasses:

```python
updated_order = replace(order, status="cancelled")
```

For nested objects:

```python
updated_customer = replace(
    customer,
    address=replace(customer.address, postcode=normalized_postcode),
)
```

For dictionaries:

```python
updated_payload = {
    **payload,
    "status": "processed",
}
```

For lists:

```python
updated_items = [
    replace(item, selected=True) if item.id == selected_item_id else item
    for item in items
]
```

---

### Pattern 7: Explicit result types for expected failures

For domain-level expected failure, prefer returning a result over throwing an exception.

Example:

```python
@dataclass(frozen=True)
class Accepted:
    value: Order


@dataclass(frozen=True)
class Rejected:
    reasons: tuple[str, ...]


OrderValidationResult = Accepted | Rejected
```

Usage:

```python
def validate_order(order: Order) -> OrderValidationResult:
    reasons = []

    if not order.lines:
        reasons.append("Order must contain at least one line")

    if order.total <= 0:
        reasons.append("Order total must be positive")

    if reasons:
        return Rejected(tuple(reasons))

    return Accepted(order)
```

Exceptions remain appropriate for:

- programmer errors;
- impossible states;
- infrastructure failures;
- truly exceptional runtime failures.

Expected business outcomes should usually be represented as values.

---

### Pattern 8: Policy functions

Business rules should be named directly.

Prefer:

```python
def can_customer_receive_discount(customer: Customer, order: Order) -> bool:
    return (
        customer.account_age_days >= 30
        and order.subtotal >= Decimal("100.00")
        and not customer.has_active_complaint
    )
```

Avoid embedding policy logic anonymously:

```python
if customer.account_age_days >= 30 and order.subtotal >= 100 and not customer.has_active_complaint:
    ...
```

Named policies make code easier to reuse and test.

---

### Pattern 9: Pure mappers between layers

Use pure mapping functions to convert between external and internal representations.

```python
def order_row_to_domain(row: OrderRow) -> Order:
    return Order(
        id=row.id,
        status=row.status,
        total=row.total,
        customer_id=row.customer_id,
    )


def order_to_response(order: Order) -> dict[str, Any]:
    return {
        "id": order.id,
        "status": order.status,
        "total": str(order.total),
        "customer_id": order.customer_id,
    }
```

Mappers should not save to the database, log, call services, or validate unrelated business rules.

---

### Pattern 10: Command and result objects

For complex workflows, prefer explicit command and result objects.

```python
@dataclass(frozen=True)
class RegisterUserCommand:
    email: str
    name: str
    accepted_terms: bool


@dataclass(frozen=True)
class RegisterUserResult:
    user_id: str
    welcome_email_queued: bool
```

This is better than passing loose positional arguments across many layers.

---

## 8. Anti-Pattern Catalogue

### Anti-pattern 1: God service

Problem:

```python
class OrderService:
    def submit_order(self, order_id):
        # loads data
        # validates order
        # calculates tax
        # applies discounts
        # charges card
        # writes database records
        # sends email
        # logs audit trail
        # publishes queue event
        ...
```

Why it is bad:

- business logic is mixed with side effects;
- behaviour is difficult to test;
- dependencies are hidden inside the class;
- refactoring risk is high;
- reuse is difficult.

Preferred refactoring:

```text
OrderService.submit_order
    → application/use_cases.py

Pure functions:
    decide_order_submission
    calculate_order_total
    validate_order
    build_payment_request
    build_confirmation_email

Infrastructure:
    OrderRepository
    PaymentClient
    EmailSender
    EventPublisher
```

---

### Anti-pattern 2: Global configuration inside business logic

Problem:

```python
def calculate_tax(amount):
    return amount * settings.TAX_RATE
```

Preferred:

```python
def calculate_tax(amount: Decimal, tax_rate: Decimal) -> Decimal:
    return amount * tax_rate
```

The shell should read `settings`.

---

### Anti-pattern 3: Hidden clock access

Problem:

```python
def is_expired(subscription):
    return subscription.expires_at < datetime.utcnow()
```

Preferred:

```python
def is_expired(subscription: Subscription, now: datetime) -> bool:
    return subscription.expires_at < now
```

The caller supplies `now`.

---

### Anti-pattern 4: Mutating objects while validating them

Problem:

```python
def validate_user(user):
    user.email = user.email.lower()

    if "@" not in user.email:
        user.errors.append("Invalid email")

    return len(user.errors) == 0
```

Preferred:

```python
@dataclass(frozen=True)
class UserValidationResult:
    normalized_user: User | None
    errors: tuple[str, ...]


def validate_user(user: User) -> UserValidationResult:
    normalized = replace(user, email=user.email.lower())
    errors = []

    if "@" not in normalized.email:
        errors.append("Invalid email")

    if errors:
        return UserValidationResult(None, tuple(errors))

    return UserValidationResult(normalized, ())
```

---

### Anti-pattern 5: Boolean flags controlling unrelated behaviour

Problem:

```python
def process_order(order, send_email=True, save=True, charge=True):
    ...
```

This often indicates too many responsibilities.

Preferred:

```python
def decide_order_processing(order: Order) -> OrderProcessingDecision:
    ...


def save_order_processing_result(
    decision: OrderProcessingDecision,
    repository: OrderRepository,
) -> None:
    ...


def send_order_notifications(
    decision: OrderProcessingDecision,
    email_sender: EmailSender,
) -> None:
    ...
```

Split decision-making from execution.

---

### Anti-pattern 6: Framework objects in domain logic

Problem:

```python
def calculate_response(request: flask.Request):
    user_id = request.json["user_id"]
    ...
```

Preferred:

```python
def calculate_response(command: CalculateResponseCommand) -> CalculateResponseResult:
    ...
```

Framework request objects should be converted at the boundary.

---

### Anti-pattern 7: Overuse of lambdas

Problem:

```python
users = sorted(
    filter(lambda u: u.active and not u.deleted, users),
    key=lambda u: (u.company.name.lower(), u.email.lower()),
)
```

Preferred:

```python
def is_visible_user(user: User) -> bool:
    return user.active and not user.deleted


def user_sort_key(user: User) -> tuple[str, str]:
    return user.company.name.lower(), user.email.lower()


users = sorted(
    [user for user in users if is_visible_user(user)],
    key=user_sort_key,
)
```

Lambdas are fine for obvious one-liners, but meaningful rules should be named.

---

### Anti-pattern 8: Clever `reduce`

Problem:

```python
result = reduce(lambda acc, x: {**acc, x.id: transform(x)}, items, {})
```

Preferred:

```python
result = {
    item.id: transform(item)
    for item in items
}
```

Use `reduce` only when the reduction is genuinely clearer than a loop, comprehension, or built-in.

---

### Anti-pattern 9: Side effects inside comprehensions

Problem:

```python
[email_sender.send(user.email) for user in users if user.active]
```

Preferred:

```python
for user in users:
    if user.active:
        email_sender.send(user.email)
```

Comprehensions should build values. They should not hide side effects.

---

### Anti-pattern 10: Unstructured utility modules

Problem:

```text
utils.py
    parse_date
    calculate_tax
    send_email
    normalize_phone
    connect_to_database
    validate_order
```

Preferred:

```text
domain/
    tax.py
    validation.py

infrastructure/
    email.py
    database.py

shared/
    dates.py
    phone_numbers.py
```

A large `utils.py` usually means the codebase lacks clear boundaries.

---

## 9. Cross-File Refactoring Example

### 9.1 Before

```text
project/
    services/
        order_service.py
    db.py
    settings.py
```

`order_service.py`:

```python
def submit_order(order_id: str) -> dict:
    order = db.fetch_order(order_id)

    if order["status"] != "draft":
        logger.warning("Order is not draft")
        return {"status": "rejected", "reason": "Order is not draft"}

    total = 0

    for line in order["lines"]:
        total += line["quantity"] * line["unit_price"]

    if total <= 0:
        logger.warning("Invalid order total")
        return {"status": "rejected", "reason": "Invalid order total"}

    tax = total * settings.TAX_RATE
    final_total = total + tax

    payment_response = payment_gateway.charge(
        order["payment_token"],
        final_total,
    )

    if not payment_response.success:
        db.update_order(order_id, {"status": "payment_failed"})
        return {"status": "payment_failed"}

    db.update_order(
        order_id,
        {
            "status": "submitted",
            "total": final_total,
            "submitted_at": datetime.utcnow(),
        },
    )

    email_sender.send(order["customer_email"], "Order submitted")

    return {"status": "submitted", "total": final_total}
```

Problems:

- raw dictionaries are used throughout;
- database access is mixed with business logic;
- payment gateway calls are mixed with calculation;
- settings are read inside the function;
- current time is read inside the function;
- logging is embedded in decision logic;
- mutation and persistence are mixed;
- the function is hard to test without patching globals.

---

### 9.2 After

```text
project/
    domain/
        orders.py
        pricing.py
        order_submission.py

    application/
        submit_order.py

    infrastructure/
        order_repository.py
        payment_gateway.py
        email_sender.py
        clock.py

    interfaces/
        http/
            order_routes.py
```

`domain/orders.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class Order:
    id: str
    status: str
    lines: tuple[OrderLine, ...]
    payment_token: str
    customer_email: str
    submitted_at: datetime | None = None
    total: Decimal | None = None
```

`domain/pricing.py`:

```python
from decimal import Decimal

from .orders import Order, OrderLine


def line_total(line: OrderLine) -> Decimal:
    return line.unit_price * line.quantity


def order_subtotal(order: Order) -> Decimal:
    return sum(line_total(line) for line in order.lines)


def order_total(order: Order, tax_rate: Decimal) -> Decimal:
    subtotal = order_subtotal(order)
    tax = subtotal * tax_rate
    return subtotal + tax
```

`domain/order_submission.py`:

```python
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from .orders import Order
from .pricing import order_total


@dataclass(frozen=True)
class PaymentRequest:
    payment_token: str
    amount: Decimal


@dataclass(frozen=True)
class SubmissionAccepted:
    updated_order: Order
    payment_request: PaymentRequest


@dataclass(frozen=True)
class SubmissionRejected:
    reason: str


SubmissionDecision = SubmissionAccepted | SubmissionRejected


def decide_order_submission(
    order: Order,
    tax_rate: Decimal,
    submitted_at: datetime,
) -> SubmissionDecision:
    if order.status != "draft":
        return SubmissionRejected("Order is not draft")

    total = order_total(order, tax_rate)

    if total <= 0:
        return SubmissionRejected("Invalid order total")

    updated_order = replace(
        order,
        status="submitted",
        total=total,
        submitted_at=submitted_at,
    )

    payment_request = PaymentRequest(
        payment_token=order.payment_token,
        amount=total,
    )

    return SubmissionAccepted(
        updated_order=updated_order,
        payment_request=payment_request,
    )
```

`application/submit_order.py`:

```python
from dataclasses import dataclass, replace
from decimal import Decimal

from project.domain.order_submission import (
    SubmissionAccepted,
    SubmissionRejected,
    decide_order_submission,
)


@dataclass(frozen=True)
class SubmitOrderCommand:
    order_id: str


@dataclass(frozen=True)
class SubmitOrderResult:
    status: str
    reason: str | None = None
    total: Decimal | None = None


@dataclass(frozen=True)
class SubmitOrderDependencies:
    order_repository: object
    payment_gateway: object
    email_sender: object
    clock: object
    tax_rate: Decimal
    logger: object


def submit_order(
    command: SubmitOrderCommand,
    deps: SubmitOrderDependencies,
) -> SubmitOrderResult:
    order = deps.order_repository.get(command.order_id)

    decision = decide_order_submission(
        order=order,
        tax_rate=deps.tax_rate,
        submitted_at=deps.clock.now(),
    )

    if isinstance(decision, SubmissionRejected):
        deps.logger.warning(decision.reason)
        return SubmitOrderResult(status="rejected", reason=decision.reason)

    payment_response = deps.payment_gateway.charge(decision.payment_request)

    if not payment_response.success:
        failed_order = replace(decision.updated_order, status="payment_failed")
        deps.order_repository.save(failed_order)
        return SubmitOrderResult(status="payment_failed")

    deps.order_repository.save(decision.updated_order)
    deps.email_sender.send(decision.updated_order.customer_email, "Order submitted")

    return SubmitOrderResult(
        status="submitted",
        total=decision.updated_order.total,
    )
```

This design is not purely functional, but it is functionally structured.

The domain decision can now be tested without:

- a database;
- payment provider;
- email service;
- logger;
- clock patching;
- environment variables.

---

## 10. Testing Requirements

### 10.1 Add characterization tests before risky changes

Before refactoring complex or poorly understood code, add tests that capture existing behaviour.

These tests may be ugly. Their job is to prevent accidental behaviour changes.

```python
def test_existing_refund_rejects_unpaid_order():
    ...
```

Once behaviour is protected, refactor.

---

### 10.2 Pure function tests should be simple

Pure function tests should not require mocks.

```python
def test_order_total_includes_tax():
    order = Order(
        id="order-1",
        status="draft",
        lines=(
            OrderLine(sku="A", quantity=2, unit_price=Decimal("10.00")),
        ),
        payment_token="token",
        customer_email="user@example.com",
    )

    assert order_total(order, Decimal("0.20")) == Decimal("24.0000")
```

If a business rule test requires extensive mocking, the code probably has not been refactored far enough.

---

### 10.3 Application tests may use fakes

Application-layer tests may use fake repositories and fake clients.

```python
class FakeOrderRepository:
    def __init__(self, order):
        self.order = order
        self.saved_order = None

    def get(self, order_id):
        return self.order

    def save(self, order):
        self.saved_order = order
```

Prefer fakes over deep mock chains where practical.

---

### 10.4 Infrastructure tests should be separate

Infrastructure tests may touch databases, filesystems, queues, or external clients.

These should not be required for every domain logic change.

---

## 11. AI Refactoring Instructions

When using an AI tool to refactor code, give it the following operating rules.

### 11.1 Preserve behaviour

The AI tool must preserve existing observable behaviour unless explicitly instructed otherwise.

Observable behaviour includes:

- return values;
- raised exceptions;
- database writes;
- emitted events;
- logs when they are operationally significant;
- HTTP response shapes;
- file output;
- ordering of side effects where ordering matters.

The tool must not silently change semantics while improving style.

---

### 11.2 Work incrementally

The AI tool should prefer small, reviewable changes.

Recommended sequence:

```text
1. Identify mixed pure/impure functions.
2. Add characterization tests where needed.
3. Extract pure calculations or decisions.
4. Move side effects outward.
5. Introduce typed data structures.
6. Replace mutation with returned values.
7. Simplify callers.
8. Remove dead or duplicated logic.
```

Avoid large rewrites unless the target module is already isolated and well-covered by tests.

---

### 11.3 Produce a refactoring note for each change

For each refactor, the AI tool should report:

```text
Files changed
Behaviour intended to preserve
Pure functions extracted
Side effects moved or isolated
Mutation removed
New types introduced
Tests added or updated
Risks / assumptions
```

This makes review easier.

---

### 11.4 Do not introduce unnecessary abstraction

The AI tool must avoid creating:

- generic pipeline frameworks;
- custom monad libraries;
- abstract base classes without multiple implementations;
- dependency injection frameworks;
- unnecessary decorators;
- excessive higher-order functions;
- clever partial application chains;
- obscure metaprogramming.

Prefer plain functions, dataclasses, protocols, and explicit arguments.

---

### 11.5 Prefer Pythonic functional constructs

Prefer:

```python
[x for x in items if predicate(x)]
```

Over:

```python
list(filter(predicate, items))
```

Prefer:

```python
[item.value for item in items]
```

Over:

```python
list(map(lambda item: item.value, items))
```

Prefer:

```python
sum(item.amount for item in items)
```

Over:

```python
reduce(lambda acc, item: acc + item.amount, items, 0)
```

Use `map`, `filter`, and `reduce` only when they clearly improve readability.

---

## 12. Refactoring Heuristics

### 12.1 Function-level candidates

A function is a strong candidate for refactoring when it does three or more of the following:

- reads from a database;
- writes to a database;
- calls an external API;
- reads settings;
- reads current time;
- generates UUIDs or random values;
- logs business decisions;
- mutates input objects;
- contains business rules;
- builds HTTP responses;
- parses raw payloads;
- sends emails;
- publishes events;
- handles retries;
- contains long conditionals;
- contains loops with state accumulation.

The likely refactoring is to extract pure logic and leave orchestration behind.

---

### 12.2 Class-level candidates

A class is a strong candidate for refactoring when it has these signs:

- many dependencies in `__init__`;
- methods call each other through mutable instance state;
- business rules depend on attributes changed by previous methods;
- the same object is used as service, cache, validator, mapper, and repository;
- tests require patching many internals;
- method order matters.

Possible refactors:

- move stateless logic to pure functions;
- convert data-heavy classes to dataclasses;
- split infrastructure dependencies from domain decisions;
- make methods return new values instead of mutating the instance.

---

### 12.3 Module-level candidates

A module is a strong candidate for splitting when it mixes these concerns:

- HTTP routes;
- database queries;
- business rules;
- serialization;
- validation;
- external API clients;
- file handling;
- formatting;
- configuration.

Split by responsibility, not by arbitrary size.

---

## 13. Detailed Pattern: Refactoring a Stateful Service Class

### 13.1 Before

```python
class ReportBuilder:
    def __init__(self, db, settings, logger):
        self.db = db
        self.settings = settings
        self.logger = logger
        self.rows = []
        self.total = 0

    def load(self, account_id):
        self.rows = self.db.fetch_rows(account_id)

    def filter(self):
        self.rows = [
            row for row in self.rows
            if row["status"] in self.settings.ALLOWED_STATUSES
        ]

    def calculate(self):
        for row in self.rows:
            self.total += row["amount"]

    def build(self):
        self.logger.info("Building report")
        return {
            "rows": self.rows,
            "total": self.total,
        }
```

Problems:

- internal mutable workflow state;
- method order matters;
- calculation depends on previous mutation;
- database access and business rules are mixed;
- settings are read inside transformation logic;
- difficult to test individual steps.

---

### 13.2 After

```python
@dataclass(frozen=True)
class ReportRow:
    status: str
    amount: Decimal


@dataclass(frozen=True)
class Report:
    rows: tuple[ReportRow, ...]
    total: Decimal


def allowed_rows(
    rows: Iterable[ReportRow],
    allowed_statuses: set[str],
) -> tuple[ReportRow, ...]:
    return tuple(
        row for row in rows
        if row.status in allowed_statuses
    )


def calculate_report_total(rows: Iterable[ReportRow]) -> Decimal:
    return sum(row.amount for row in rows)


def build_report(
    rows: Iterable[ReportRow],
    allowed_statuses: set[str],
) -> Report:
    filtered_rows = allowed_rows(rows, allowed_statuses)
    total = calculate_report_total(filtered_rows)

    return Report(
        rows=filtered_rows,
        total=total,
    )
```

Shell:

```python
def build_account_report(
    account_id: str,
    repository: ReportRepository,
    settings: Settings,
    logger: Logger,
) -> Report:
    logger.info("Building report for account %s", account_id)

    rows = repository.fetch_rows(account_id)

    return build_report(
        rows=rows,
        allowed_statuses=settings.allowed_statuses,
    )
```

This removes workflow mutation and makes the report calculation independently testable.

---

## 14. Handling Classes in Functional Python

Functional refactoring does not mean removing classes.

Use classes for:

- domain data;
- protocols/interfaces;
- infrastructure clients;
- repositories;
- framework adapters;
- cohesive stateful resources;
- objects whose identity matters.

Prefer functions for:

- calculations;
- validation;
- transformations;
- policies;
- decisions;
- formatting;
- mapping between representations.

A good split:

```python
class SqlOrderRepository:
    def get(self, order_id: str) -> Order:
        ...

    def save(self, order: Order) -> None:
        ...


def calculate_order_total(order: Order, tax_rate: Decimal) -> Decimal:
    ...


def can_submit_order(order: Order) -> bool:
    ...
```

A less desirable split:

```python
class OrderCalculator:
    def calculate_order_total(self, order):
        ...


class OrderValidator:
    def can_submit_order(self, order):
        ...
```

Stateless classes that only contain one or two methods are often unnecessary.

---

## 15. Error Handling Guidance

### 15.1 Use values for expected business failures

Expected business failures include:

- invalid order;
- insufficient balance;
- user not eligible;
- unsupported region;
- expired subscription;
- duplicate registration;
- missing required field.

Represent these as return values.

```python
@dataclass(frozen=True)
class Eligible:
    pass


@dataclass(frozen=True)
class NotEligible:
    reasons: tuple[str, ...]


EligibilityResult = Eligible | NotEligible
```

---

### 15.2 Use exceptions for exceptional or infrastructure failures

Exceptions are appropriate for:

- database unavailable;
- network timeout;
- unexpected response format;
- invariant violation;
- programmer error;
- corrupt internal state.

Application services may catch infrastructure exceptions and convert them into application-level results where appropriate.

---

### 15.3 Do not use exceptions as normal control flow inside pure domain logic

Avoid:

```python
def validate_order(order):
    if not order.lines:
        raise ValueError("Order must contain lines")
```

Prefer:

```python
def validate_order(order: Order) -> ValidationResult:
    if not order.lines:
        return Invalid(("Order must contain lines",))

    return Valid(order)
```

Exceptions are acceptable when invalid input indicates a programmer error rather than a user-correctable business condition.

---

## 16. Type Guidance

### 16.1 Use type hints for extracted functions

Every newly extracted function should have type annotations.

Preferred:

```python
def calculate_tax(amount: Decimal, tax_rate: Decimal) -> Decimal:
    return amount * tax_rate
```

Avoid:

```python
def calculate_tax(amount, tax_rate):
    return amount * tax_rate
```

---

### 16.2 Use domain-specific types where they clarify intent

Instead of passing multiple strings:

```python
def send_email(email, subject, body):
    ...
```

Prefer:

```python
@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    body: str
```

Then:

```python
def build_welcome_email(user: User) -> EmailMessage:
    ...
```

The builder can be pure. The sender remains impure.

---

### 16.3 Use protocols for infrastructure dependencies

```python
from typing import Protocol


class OrderRepository(Protocol):
    def get(self, order_id: str) -> Order:
        ...

    def save(self, order: Order) -> None:
        ...
```

This allows application logic to depend on behaviour rather than concrete classes.

---

## 17. Dependency Management

### 17.1 Dependencies should point inward

Preferred direction:

```text
interfaces      → application → domain
infrastructure  → domain
application     → domain
```

Avoid:

```text
domain → infrastructure
domain → interfaces
domain → settings
domain → database
```

The domain layer should not import the database, web framework, task queue, or settings module.

---

### 17.2 Configuration should be read once near the edge

Before:

```python
def retry_count():
    return settings.RETRY_COUNT


def calculate_timeout():
    return settings.BASE_TIMEOUT * retry_count()
```

After:

```python
@dataclass(frozen=True)
class RetryPolicy:
    retry_count: int
    base_timeout_seconds: int


def calculate_timeout(policy: RetryPolicy) -> int:
    return policy.base_timeout_seconds * policy.retry_count
```

Infrastructure or application startup code builds the policy from settings.

---

## 18. Collection Processing Guidance

Use comprehensions for straightforward transformations.

```python
normalized_names = [name.strip().lower() for name in names]
```

Use generator expressions when only one pass is needed.

```python
total = sum(line.amount for line in lines)
```

Use named functions when predicates or transformations are meaningful.

```python
def is_billable(line: InvoiceLine) -> bool:
    return line.status == "billable" and line.amount > 0
```

Then:

```python
billable_total = sum(
    line.amount
    for line in lines
    if is_billable(line)
)
```

Use loops when:

- multiple accumulators are required;
- error handling is clearer imperatively;
- early exits are important;
- the comprehension would become dense;
- performance or memory concerns matter.

Functional Python permits clear loops. The problem is not loops. The problem is hidden, tangled state.

---

## 19. Naming Conventions

### 19.1 Names for pure functions

Good names for pure functions:

```text
calculate_...
derive_...
normalize_...
validate_...
select_...
filter_...
group_...
summarize_...
build_...
to_...
from_...
can_...
is_...
has_...
decide_...
```

### 19.2 Names for impure functions

Good names for impure functions:

```text
load_...
fetch_...
save_...
send_...
publish_...
write_...
read_...
persist_...
call_...
execute_...
handle_...
```

This naming distinction makes side effects easier to spot.

Avoid naming an impure function as if it were pure.

Bad:

```python
def get_total(order_id):
    order = db.fetch_order(order_id)
    ...
```

Better:

```python
def fetch_order_total(order_id, repository):
    ...
```

Best split:

```python
def calculate_order_total(order):
    ...


def fetch_and_calculate_order_total(order_id, repository):
    ...
```

---

## 20. Review Checklist

A refactor is acceptable when the answer to most of these questions is yes.

### Behaviour

- Does the refactor preserve existing observable behaviour?
- Are tests added or updated?
- Are business rules still equivalent?
- Are edge cases preserved?

### Purity

- Were pure calculations extracted from impure workflows?
- Can the core logic be tested without mocks?
- Are time, randomness, settings, and external data passed in explicitly?

### Side effects

- Are database calls present only in appropriate layers?
- Are API calls isolated?
- Is logging outside pure decision functions?
- Are side effects ordered explicitly where order matters?

### Data

- Are domain concepts represented with typed data where useful?
- Is mutation reduced?
- Are input objects left unchanged unless mutation is explicit?

### Design

- Is the new design simpler than the old design?
- Are names clearer?
- Are modules more cohesive?
- Is abstraction justified by actual reuse or complexity reduction?

### Python quality

- Is the result idiomatic Python?
- Are comprehensions used where clear?
- Are loops retained where clearer?
- Is clever functional style avoided?

---

## 21. AI Prompt Template

Use the following prompt when asking an AI coding tool to refactor part of the codebase.

```text
Refactor the selected Python code toward a functional core / imperative shell structure.

Follow these rules:

1. Preserve existing observable behaviour.
2. Do not perform a large rewrite unless necessary.
3. Identify business logic currently mixed with side effects.
4. Extract pure or mostly pure functions for calculations, validation, transformation, and decisions.
5. Move database access, network calls, filesystem access, logging, clock access, randomness, and settings access toward the outer shell.
6. Pass dependencies and external values explicitly.
7. Avoid mutating input objects unless the function name and purpose explicitly indicate mutation.
8. Prefer dataclasses with frozen=True for domain data where appropriate.
9. Prefer clear Python comprehensions, generator expressions, and built-ins over forced map/filter/reduce style.
10. Keep loops when they are clearer than functional expressions.
11. Avoid introducing unnecessary abstractions, frameworks, decorators, or clever FP constructs.
12. Add or update tests for extracted pure functions and changed application workflows.

For the final response, provide:

- files changed;
- pure functions extracted;
- side effects isolated;
- mutation removed or retained with justification;
- tests added or recommended;
- any assumptions or risks.
```

---

## 22. Refactoring Priority Guide

### 22.1 Highest-value refactors

Start with code that has:

- important business rules;
- frequent bugs;
- difficult tests;
- heavy mocking;
- high change frequency;
- mixed database/API/business logic;
- complex conditionals;
- repeated calculations;
- significant mutation.

These areas benefit most from functional restructuring.

---

### 22.2 Lower-value refactors

Deprioritize:

- stable infrastructure wrappers;
- simple CRUD endpoints;
- thin adapters;
- one-off migration scripts;
- performance-critical loops that are already clear;
- generated code;
- framework boilerplate.

Not all code needs functional refactoring.

---

## 23. Final Operating Rule

When uncertain, the AI tool should prefer:

- plain functions over clever abstractions;
- explicit data flow over hidden state;
- values over mutation;
- pure decisions over side effects;
- small safe refactors over large rewrites;
- Pythonic clarity over functional purity.

The purpose of this refactoring programme is not to make the codebase academically functional. The purpose is to make it easier for humans and AI tools to understand, test, modify, and extend safely.

