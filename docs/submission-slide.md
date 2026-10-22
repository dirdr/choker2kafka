# Sentinel

### From Kafka contract breach to verified repair

For data platform teams and SREs who need trustworthy streams without manual incident archaeology.

| The problem | Why now | First users |
|---|---|---|
| Events can pass schema validation and still break downstream assumptions. | Agents can connect stream evidence, contracts and producer changes, then propose a reviewable fix. | Pilot with Kafka teams in Aiven and open-source communities. Start with one producer and one contract. |

**Commit a fault → detect the breach → investigate evidence → open a repair PR → merge → verify recovery**

**Data layer:** Aiven Kafka carries events. Aiven PostgreSQL stores contracts, producer revisions, frozen incident evidence, tool activity and recovery proof. Claude reads evidence through typed tools.

**Evidence:** An integer type check accepts the faulty timestamp. Sentinel identifies the contract breach and verifies two fresh passing windows after the repair.

**Measured demo:** detection **[fill]** · investigation **[fill]** · tokens **[fill]** · verified recovery **[fill]**
