import psycopg2
import re
import traceback
from sets import Set
from ripplelogin import dbname, dbuser, dbpass
from spock.mcp.mcpacket import Packet
from decimal import *

class RipplePlugin:
    def __init__(self, client):
        self.conn = psycopg2.connect(database = dbname, user = dbuser, password = dbpass)
        self.cur = self.conn.cursor()
        self.cur.execute("SET timezone = 'UTC';")
        self.conn.commit()
        self.client = client
        client.register_dispatch(self.chat_received, 0x03)
    
    def chat_received(self, packet):
        try:
            msg = packet.data['text']
            msg = re.sub('\xa7.', '', msg)
            match = re.search('^From ([A-Za-z0-9]+): ([A-Za-z0-9]+)(.*)', msg)
            #match = re.search('^([A-Za-z0-9]+) whispers ([A-Za-z0-9]+)(.*)', msg)
            if match:
                self.cur = self.conn.cursor()
                sender = match.group(1)
                command = match.group(2)
                remaining = match.group(3)
                if command == 'register':
                    if self.check_account(0, sender):
                        self.send_pm(sender, "You are already registered :)")
                    else:
                        self.register_account(sender)
                elif command == 'trust':
                    arg_match = re.search('^ ([A-Za-z0-9]+) ([0-9]+(?:\.[0-9]{1,2})?)([di])', remaining)
                    if arg_match:
                        trustee = arg_match.group(1)
                        if trustee == sender:
                            self.send_pm(sender, "You can't loan yourself money")
                        else:
                            amount = Decimal(arg_match.group(2))
                            if amount > 0:
                                if self.check_account(sender, sender) and self.check_account(sender, trustee):
                                    self.add_trust(sender, trustee, amount, arg_match.group(3))
                                    self.show_trusts(sender)
                            else:
                                self.send_pm(sender, "You can only trust a positive amount. Nice try :)")
                    else:
                        self.send_pm(sender, "Usage: trust <person> <amount>d")
                elif command == 'reducetrust':
                    arg_match = re.search('^ ([A-Za-z0-9]+) (?:([0-9]+(?:\.[0-9]{1,2})?)([di]))?', remaining)
                    if arg_match:
                        trustee = arg_match.group(1)
                        amount = abs(Decimal(arg_match.group(2)))
                        if self.check_account(sender, sender) and self.check_account(sender, trustee):
                            self.reduce_trust(sender, trustee, amount, arg_match.group(3))
                    else:
                        self.send_pm(sender, "Usage: reducetrust <person> <amount>d")
                elif command == 'pay':
                    arg_match = re.search('^ ([A-Za-z0-9]+) ([0-9]+(?:\.[0-9]{1,2})?)([di])', remaining)
                    if arg_match:
                        recipient = arg_match.group(1)
                        amount = Decimal(arg_match.group(2))
                        if amount > 0:
                            if self.check_account(sender, sender) and self.check_account(sender, recipient):
                                self.send_payment(sender, recipient, amount, arg_match.group(3))
                        else:
                            self.send_pm(sender, "You can only pay a positive amount. Nice try :)")
                    else:
                        self.send_pm(sender, "Usage: pay <person> <amount>d")
                elif command == 'transactions':
                    arg_match = re.search('^ --all', remaining)
                    if arg_match:
                        if self.check_account(sender, sender):
                            self.show_all_transactions(sender)
                    elif remaining == '':
                        if self.check_account(sender, sender):
                            self.show_direct_transactions(sender)
                    else:
                        self.send_pm(sender, "Usage: transactions [--all]")
                elif command == 'trusts':
                    if self.check_account(sender, sender):
                        self.show_trusts(sender)
                elif command == 'debts':
                    if self.check_account(sender, sender):
                        self.show_debts(sender)
                elif command == 'owed':
                    if self.check_account(sender, sender):
                        self.show_owed(sender)
                else:
                    self.send_pm(sender, "Command not understood: %s" % (command))
        except Exception as error:
            print "Error handling command %s: %s" % (msg, error)
            print traceback.format_exc()
            try:
                self.conn.rollback()
            except:
                pass
    
    def send_pm(self, user, message):
        self.client.push(Packet(ident=0x03, data={'text':"/msg %s %s" % (user, message)}))
        
    def check_account(self, invoker, account):
        self.cur.execute("""SELECT 1 FROM accounts WHERE account_name = (%s)""", (account,))
        row = self.cur.fetchone()
        if not row:
            if invoker:
                self.send_pm(invoker, "%s has not registered for ripple pay" % (account,))
            return 0
        return 1
        
    def show_trusts(self, account):
        self.cur.execute("""SELECT trustee, amount, currency FROM trusts WHERE trustor = %s ORDER BY trustee""", (account,))
        trusts = []
        for row in self.cur.fetchall():
            trusts.append("%s (%0.2f%s)" % row)
        self.send_pm(account, "You trust: " + ', '.join(trusts))
        
    def show_debts(self, account):
        self.cur.execute("""SELECT debt_to, amount, currency FROM debts WHERE debt_from = %s ORDER BY debt_to""", (account,))
        trusts = []
        for row in self.cur.fetchall():
            trusts.append("%s (%0.2f%s)" % row)
        self.send_pm(account, "You owe: " + ', '.join(trusts))
        
    def show_owed(self, account):
        self.cur.execute("""SELECT debt_from, amount, currency FROM debts WHERE debt_to = %s ORDER BY debt_from""", (account,))
        trusts = []
        for row in self.cur.fetchall():
            trusts.append("%s (%0.2f%s)" % row)
        self.send_pm(account, "You are owed: " + ', '.join(trusts))
    
    def register_account(self, sender):
        self.cur.execute("""INSERT INTO accounts (account_name) VALUES (%s)""", (sender,))
        self.conn.commit()
        self.send_pm(sender, "Ripple account registered. You may now use this in-game ripple pay system.")
        self.send_pm(sender, "The network operator gives no guarantees and takes no responsibility for errors whatsoever.")
    
    def show_direct_transactions(self, sender):
        self.cur.execute("""SELECT sent_at, sent_from, sent_to, amount, currency FROM transactions WHERE (sent_from = %s OR sent_to = %s) AND sent_at > NOW() - '1 week'::interval ORDER BY sent_at DESC LIMIT 5""", (sender, sender))
        for row in self.cur.fetchall():
            self.send_pm(sender, "[%s] %0.2f%s %s -> %s" % (row[0].strftime("%Y-%m-%d %H:%M:%S"), row[3], row[4], row[1], row[2]))
    
    def show_all_transactions(self, sender):
        self.cur.execute("""SELECT DISTINCT transaction_paths.transaction_id, transactions.sent_at, transaction_paths.amount, transactions.currency, transaction_paths.path FROM shifts JOIN transaction_paths USING (transaction_id, path_id) JOIN transactions ON (shifts.transaction_id = transactions.transaction_id) WHERE from_account = %s OR to_account = %s AND sent_at > NOW() - '1 week'::interval ORDER BY sent_at DESC LIMIT 10""", (sender,sender))
        for row in self.cur.fetchall():
            self.send_pm(sender, "[%s] sent %0.2f%s through (%s)" % (row[1].strftime("%Y-%m-%d %H:%M:%S"), row[2], row[3], ', '.join(row[4])))
    
    def add_trust(self, trustor, trustee, amount, currency):
        self.cur.execute("""SELECT 1 FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
        row = self.cur.fetchone()
        if row:
            self.cur.execute("""UPDATE trusts SET amount = amount + %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
        else:
            self.cur.execute("""INSERT INTO trusts (trustor, trustee, amount, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
        self.cur.execute("""INSERT INTO trust_changes (trustor, trustee, changed_by, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
        self.conn.commit()
    
    def reduce_trust(self, trustor, trustee, amount, currency):
        self.cur.execute("""SELECT amount FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
        row = self.cur.fetchone()
        if row:
            if row[0] > amount:
                self.conn.commit()
                self.cur.execute("""UPDATE trusts SET amount = amount - %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
                self.cur.execute("""INSERT INTO trust_changes (trustor, trustee, changed_by, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
                self.conn.commit()
                self.send_pm(trustor, "Reduced trust in %s by %f" % (trustee, amount))
            else:
                self.cur.execute("""INSERT INTO trust_changes (trustor, trustee, changed_by, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, -row[0], currency))
                self.cur.execute("""DELETE FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
                self.conn.commit()
                self.send_pm(trustor, "Revoked trust in %s" % (trustee))
    
    def send_payment(self, sender, recipient, amount, currency):
        paths = self.find_paths(sender, recipient, amount, currency)
        total_amount = 0
        for pair in paths:
            total_amount += pair[1]
        if total_amount == amount:
            self.transact_paths(sender, recipient, amount, paths, currency)
            self.send_pm(sender, "Sent %0.2f%s to %s" % (amount, currency, recipient))
            self.send_pm(recipient, "%s sent you %0.2f%s" % (sender, amount, currency))
        else:
            self.send_pm(sender, "Could not send payment of %0.2f%s to %s, maximum is %0.2f%s" % (amount, currency, recipient, total_amount, currency))
    
    def reject_owed(self, trustee, trustor, amount, currency):
        # TODO: Reject a debt owed by someone who trusts you
        # Creates permanent record and destroys trust link
        pass
    
    def find_paths(self, sender, recipient, amount, currency):
        expand_set = Set([sender])
        edge_paths = [[sender]]
        paths = []
        while expand_set:
            available_links = Set()
            # Follow paths of repaying debt
            self.cur.execute("""SELECT debt_to, debt_from FROM debts WHERE currency = %s AND debt_to IN (%s)""", (currency, tuple(expand_set)))
            for row in self.cur.fetchall():
                available_links.add(row)
                
            # Follow paths of trusted debt acquisition
            self.cur.execute("""SELECT trustee, trustor FROM trusts WHERE currency = %s AND trustee IN (%s)""", (currency, tuple(expand_set)))
            for row in self.cur.fetchall():
                available_links.add(row)
            
            next_paths = []
            next_nodes = Set()
            for path in edge_paths:
                for link in available_links:
                    if link[0] == path[-1]:
                        if link[1] == recipient:
                            # Reached the recipient - measure capacity
                            new_path = path[:]
                            new_path.append(link[1])
                            bottleneck = self.find_bottleneck(new_path, currency, paths)
                            if bottleneck == None or bottleneck >= amount:
                                paths.append((new_path, amount))
                                return paths
                            elif bottleneck != None and bottleneck > 0:
                                # We can only send part along this path
                                paths.append((new_path, bottleneck))
                                amount -= bottleneck
                        elif link[1] not in path:
                            new_path = path[:]
                            new_path.append(link[1])
                            next_paths.append(new_path)
                            next_nodes.add(link[1])
            expand_set = next_nodes
            edge_paths = next_paths
        return paths
    
    def find_bottleneck(self, path, currency, prior_paths):
        # Find how much we can send along a path
        limit = None
        from_account = path[0]
        for to_account in path[1:]:
            link_limit = self.find_max_trusted_transfer(from_account, to_account, currency)
            for pair in prior_paths:
                path = pair[0]
                prior_amount = pair[1]
                if from_account in path and path[path.index(from_account)+1] == to_account:
                    # Prior path has this link in it
                    link_limit = link_limit - prior_amount
            if link_limit <= 0:
                return 0
            if limit == None or link_limit < limit:
                limit = link_limit
            from_account = to_account
        return limit
    
    def find_max_trusted_transfer(self, from_account, to_account, currency):
        trusted_amount = 0
        self.cur.execute("""SELECT amount FROM trusts WHERE currency = %s AND trustor = %s AND trustee = %s""", (currency, to_account, from_account))
        for row in self.cur.fetchall():
            trusted_amount += row[0]
        
        already_used = 0
        self.cur.execute("""SELECT amount FROM debts WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (from_account, to_account, currency))
        for row in self.cur.fetchall():
            already_used += row[0]
        
        back_owed = 0
        self.cur.execute("""SELECT amount FROM debts WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (to_account, from_account, currency))
        for row in self.cur.fetchall():
            back_owed += row[0]
        
        print (from_account, to_account, currency, trusted_amount, back_owed, already_used)
        return max(0, trusted_amount + back_owed - already_used)
    
    def transact_paths(self, sender, recipient, amount, paths, currency):
        # Log record
        self.cur.execute("""INSERT INTO transactions (sent_from, sent_to, amount, currency) VALUES (%s, %s, %s, %s) RETURNING transaction_id""", (sender, recipient, amount, currency))
        transaction_id = self.cur.fetchone()[0]
        
        for path_id, pair in enumerate(paths):
            print pair
            path = pair[0]
            amount = pair[1]
            
            # Record path log record
            self.cur.execute("""INSERT INTO transaction_paths (transaction_id, path_id, path, amount) VALUES (%s, %s, %s, %s)""", (transaction_id, path_id, path, amount))
            
            from_account = path[0]
            for to_account in path[1:]:
                self.cur.execute("""INSERT INTO shifts (transaction_id, path_id, from_account, to_account)   VALUES (%s, %s, %s, %s)""", (transaction_id, path_id, from_account, to_account))
                self.shift_amount_pair(from_account, to_account, amount, currency)
                from_account = to_account
        self.conn.commit()
    
    def shift_amount_pair(self, from_account, to_account, amount, currency):
        # First erase debt
        self.cur.execute("""SELECT amount FROM debts WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (to_account, from_account, currency))
        for row in self.cur.fetchall():
            if row[0] >= amount:
                self.cur.execute("""UPDATE debts SET amount = amount - %s WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (amount, to_account, from_account, currency))
                return
            else:
                self.cur.execute("""DELETE FROM debts WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (to_account, from_account, currency))
                amount -= row[0]
        if amount >= 0:
            # Still have amount to fulfill
            self.cur.execute("""SELECT amount FROM debts WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (from_account, to_account, currency))
            row = self.cur.fetchone()
            if row:
                self.cur.execute("""UPDATE debts SET amount = amount + %s WHERE debt_from = %s AND debt_to = %s AND currency = %s""", (amount, from_account, to_account, currency))
            else:
                self.cur.execute("""INSERT INTO debts (debt_from, debt_to, amount, currency) VALUES (%s, %s, %s, %s)""", (from_account, to_account, amount, currency))
