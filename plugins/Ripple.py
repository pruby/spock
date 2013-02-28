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
        self.current_accounts = {}
        client.register_dispatch(self.chat_received, 0x03)
        client.register_dispatch(self.player_list_update, 0xC9)
    
    def player_list_update(self, packet):
        try:
            # Delete current account entry on logout
            if packet.data['online'] == False:
                player = packet.data['player_name']
                if player in self.current_accounts:
                    del self.current_accounts[player]
        except Exception as error:
            print "Error handling command %s: %s" % (msg, error)
            print traceback.format_exc()
            try:
                self.conn.rollback()
            except:
                pass
    
    def chat_received(self, packet):
        try:
            msg = packet.data['text']
            msg = re.sub('\xa7.', '', msg)
            match = re.search('^From ([A-Za-z0-9_]+): ([A-Za-z0-9]+)(.*)', msg)
            #match = re.search('^([A-Za-z0-9]+) whispers ([A-Za-z0-9]+)(.*)', msg)
            if match:
                sender = match.group(1)
                command = match.group(2)
                remaining = match.group(3)
                account = self.current_account(sender)
                if command == 'register':
                    arg_match = re.search('^ (@[A-Za-z0-9_]+)', remaining)
                    if arg_match:
                        account = arg_match.group(1)
                    if self.check_account(0, account):
                        self.send_pm(sender, "That account is already registered :)")
                    else:
                        self.register_account(sender, account)
                elif command == 'use':
                    arg_match = re.search('^ (@[A-Za-z0-9_]+)', remaining)
                    if arg_match:
                        account = arg_match.group(1)
                        self.switch_account(sender, account)
                    elif remaining == '':
                        self.switch_account(sender, sender)
                    else:
                        self.send_pm(sender, "Usage: account [@<group>]")
                elif command == 'addmanager':
                    arg_match = re.search('^ ([A-Za-z0-9_]+)', remaining)
                    if account == sender:
                        self.send_pm(sender, "You can't grant others access to your personal account")
                    elif arg_match:
                        other = arg_match.group(1)
                        self.add_manager(sender, account, other)
                    else:
                        self.send_pm(sender, "Usage: grant [<group>]")
                elif command == 'removemanager':
                    arg_match = re.search('^ ([A-Za-z0-9_]+)', remaining)
                    if account == sender:
                        self.send_pm(sender, "You can't resign access to your personal account")
                    elif arg_match:
                        other = arg_match.group(1)
                        if other == sender:
                            self.send_pm(sender, "You can't remove yourself as manager. Get another manager to remove you.")
                        else:
                            self.remove_manager(sender, account, other)
                    else:
                        self.send_pm(sender, "Usage: grant [<group>]")
                elif command == 'trust':
                    arg_match = re.search('^ (@?[A-Za-z0-9_]+) ([0-9]+(?:\.[0-9]{1,2})?)([a-z]+)', remaining)
                    if arg_match:
                        trustee = arg_match.group(1)
                        if trustee == account:
                            self.send_pm(sender, "You can't loan yourself money")
                        else:
                            amount = Decimal(arg_match.group(2))
                            currency = arg_match.group(3)
                            if amount > 0:
                                if not (self.check_account(sender, account) and self.check_account(sender, trustee)):
                                    pass
                                elif not self.check_currency(sender, currency):
                                    pass
                                else:
                                    self.add_trust(sender, trustee, amount, currency)
                                    self.show_trusts(sender)
                            else:
                                self.send_pm(sender, "You can only trust a positive amount. Nice try :)")
                    else:
                        self.send_pm(sender, "Usage: trust <person> <amount><currency>")
                elif command == 'reducetrust':
                    arg_match = re.search('^ (@?[A-Za-z0-9_]+) (?:([0-9]+(?:\.[0-9]{1,2})?)([a-z]+))?', remaining)
                    if arg_match:
                        trustee = arg_match.group(1)
                        amount = abs(Decimal(arg_match.group(2)))
                        currency = arg_match.group(3)
                        if not (self.check_account(sender, account) and self.check_account(sender, trustee)):
                            pass
                        elif not self.check_currency(sender, currency):
                            pass
                        else:
                            self.reduce_trust(sender, trustee, amount, currency)
                    else:
                        self.send_pm(sender, "Usage: reducetrust <person> <amount>d")
                elif command == 'pay':
                    arg_match = re.search('^ (@?[A-Za-z0-9_]+) ([0-9]+(?:\.[0-9]{1,2})?)([a-z]+)', remaining)
                    if arg_match:
                        recipient = arg_match.group(1)
                        amount = Decimal(arg_match.group(2))
                        currency = arg_match.group(3)
                        if amount > 0:
                            if not (self.check_account(sender, account) and self.check_account(sender, recipient)):
                                pass
                            elif not self.check_currency(sender, currency):
                                pass
                            else:
                                self.send_payment(sender, recipient, amount, currency)
                        else:
                            self.send_pm(sender, "You can only pay a positive amount. Nice try :)")
                    else:
                        self.send_pm(sender, "Usage: pay <person> <amount><currency>")
                elif command == 'transactions':
                    arg_match = re.search('^ --all', remaining)
                    if arg_match:
                        if self.check_account(sender, account):
                            self.show_all_transactions(sender)
                    elif remaining == '':
                        if self.check_account(sender, account):
                            self.show_direct_transactions(sender)
                    else:
                        self.send_pm(sender, "Usage: transactions [--all]")
                elif command == 'trusts':
                    if self.check_account(sender, account):
                        self.show_trusts(sender)
                elif command == 'groupinfo':
                    arg_match = re.search('^ (@[A-Za-z0-9_]+)', remaining)
                    if arg_match:
                        account = arg_match.group(1)
                        self.group_info(sender, account)
                    else:
                        self.send_pm(sender, "Usage: groupinfo @<group>")
                elif command == 'trustsme':
                    if self.check_account(sender, account):
                        self.show_trustsme(sender)
                elif command == 'accounts':
                    self.show_accounts(sender)
                elif command == 'debts':
                    if self.check_account(sender, account):
                        self.show_debts(sender)
                elif command == 'owed':
                    if self.check_account(sender, account):
                        self.show_owed(sender)
                elif command == 'whoami':
                    self.send_pm(sender, "Using account %s" % (account,))
                else:
                    self.send_pm(sender, "Command not understood: %s" % (command))
        except Exception as error:
            print "Error handling command %s: %s" % (msg, error)
            print traceback.format_exc()
            try:
                self.conn.rollback()
            except:
                pass
    
    def current_account(self, user):
      if user in self.current_accounts:
          return self.current_accounts[user]
      else:
          return user
    
    def send_pm(self, user, message):
        lengthLimit = 100
        prefix = "/msg %s " % (user,)
        chunkSize = lengthLimit - len(prefix)
        for i in xrange(0, len(message) - 1, chunkSize):
            self.client.push(Packet(ident=0x03, data={'text':prefix + message[i:min(i+chunkSize,len(message))]}))
        
    def check_account(self, invoker, account):
        self.cur.execute("""SELECT 1 FROM accounts WHERE account_name = (%s)""", (account,))
        row = self.cur.fetchone()
        if not row:
            if invoker:
                self.send_pm(invoker, "%s has not registered for ripple pay" % (account,))
            return 0
        return 1
        
    def check_currency(self, invoker, currency):
        self.cur.execute("""SELECT 1 FROM currencies WHERE currency_name = (%s)""", (currency,))
        row = self.cur.fetchone()
        if not row:
            if invoker:
                self.send_pm(invoker, "%s is not a registered currency" % (currency,))
            return 0
        return 1
        
    def show_trusts(self, invoker):
        account = self.current_account(invoker)
        self.cur.execute("""SELECT trustee, amount, currency FROM trusts WHERE trustor = %s ORDER BY trustee""", (account,))
        trusts = []
        for row in self.cur.fetchall():
            trusts.append("%s (%0.2f%s)" % row)
        self.send_pm(invoker, account + " trusts: " + ', '.join(trusts))
    
    def group_managers(self, group):
        self.cur.execute("""SELECT minecraft_name FROM account_managers WHERE account_name = %s ORDER BY minecraft_name""", (group,))
        managers = []
        for row in self.cur.fetchall():
            managers.append(row[0])
        return managers
    
    def add_manager(self, invoker, group, new_manager):
        self.cur.execute("""INSERT INTO account_managers (account_name, minecraft_name) VALUES (%s, %s)""", (group, new_manager))
        self.send_pm(invoker, "Made %s a manager of %s" % (new_manager, group))
    
    def remove_manager(self, invoker, group, ex_manager):
        if ex_manager in self.group_managers(group):
            self.cur.execute("""DELETE FROM account_managers WHERE account_name = %s AND minecraft_name = %s""", (group, ex_manager))
            self.send_pm(invoker, "%s is no longer a manager of %s" % (ex_manager, group))
        else:
            self.send_pm(invoker, "%s is not a manager of %s" % (ex_manager, group))
        
    def group_info(self, invoker, group):
        managers = self.group_managers(group)
        self.send_pm(invoker, group + " is managed by: " + ', '.join(managers))
        
    def show_accounts(self, invoker):
        self.cur.execute("""SELECT account_name FROM account_managers WHERE minecraft_name = %s ORDER BY account_name""", (invoker,))
        accounts = []
        for row in self.cur.fetchall():
            accounts.append(row[0])
        self.send_pm(invoker, "You manage: " + ', '.join(accounts))
        
    def show_trustsme(self, invoker):
        account = self.current_account(invoker)
        self.cur.execute("""SELECT trustor, amount, currency FROM trusts WHERE trustee = %s ORDER BY trustee""", (account,))
        trusts = []
        for row in self.cur.fetchall():
            trusts.append("%s (%0.2f%s)" % row)
        self.send_pm(invoker, account + " is trusted by: " + ', '.join(trusts))
        
    def show_debts(self, invoker):
        account = self.current_account(invoker)
        self.cur.execute("""SELECT debt_to, amount, currency FROM debts WHERE debt_from = %s ORDER BY debt_to""", (account,))
        trusts = []
        for row in self.cur.fetchall():
            trusts.append("%s (%0.2f%s)" % row)
        self.send_pm(invoker, account + " owes: " + ', '.join(trusts))
        
    def show_owed(self, invoker):
        account = self.current_account(invoker)
        self.cur.execute("""SELECT debt_from, amount, currency FROM debts WHERE debt_to = %s ORDER BY debt_from""", (account,))
        trusts = []
        for row in self.cur.fetchall():
            trusts.append("%s (%0.2f%s)" % row)
        self.send_pm(invoker, account + " is owed: " + ', '.join(trusts))
    
    def switch_account(self, invoker, account):
        managers = self.group_managers(account)
        if invoker not in managers:
            self.send_pm(invoker, "You do not manage account %s" % (account,))
        else:
            self.current_accounts[invoker] = account
            self.send_pm(invoker, "Using account %s" % (account,))
    
    def register_account(self, invoker, account):
        self.cur.execute("""INSERT INTO accounts (account_name) VALUES (%s)""", (account,))
        self.cur.execute("""INSERT INTO account_managers (account_name, minecraft_name) VALUES (%s, %s)""", (account,invoker))
        self.conn.commit()
        self.send_pm(invoker, "Ripple account registered. You may now use this in-game ripple pay system.")
        self.send_pm(invoker, "The network is run on a best-effort approach. No guarantees, no liability.")
    
    def show_direct_transactions(self, invoker):
        account = self.current_account(invoker)
        self.cur.execute("""SELECT sent_at, sent_from, sent_to, amount, currency FROM transactions WHERE (sent_from = %s OR sent_to = %s) AND sent_at > NOW() - '1 week'::interval ORDER BY sent_at DESC LIMIT 5""", (account, account))
        for row in self.cur.fetchall():
            self.send_pm(invoker, "[%s] %0.2f%s %s -> %s" % (row[0].strftime("%Y-%m-%d %H:%M:%S"), row[3], row[4], row[1], row[2]))
    
    def show_all_transactions(self, invoker):
        account = self.current_account(invoker)
        self.cur.execute("""SELECT DISTINCT transaction_paths.transaction_id, transactions.sent_at, transaction_paths.amount, transactions.currency, transaction_paths.path FROM shifts JOIN transaction_paths USING (transaction_id, path_id) JOIN transactions ON (shifts.transaction_id = transactions.transaction_id) WHERE from_account = %s OR to_account = %s AND sent_at > NOW() - '1 week'::interval ORDER BY sent_at DESC LIMIT 10""", (account,account))
        for row in self.cur.fetchall():
            self.send_pm(invoker, "[%s] sent %0.2f%s through (%s)" % (row[1].strftime("%Y-%m-%d %H:%M:%S"), row[2], row[3], ', '.join(row[4])))
    
    def add_trust(self, invoker, trustee, amount, currency):
        trustor = self.current_account(invoker)
        self.cur.execute("""SELECT 1 FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
        row = self.cur.fetchone()
        if row:
            self.cur.execute("""UPDATE trusts SET amount = amount + %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
        else:
            self.cur.execute("""INSERT INTO trusts (trustor, trustee, amount, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
        self.cur.execute("""INSERT INTO trust_changes (trustor, trustee, changed_by, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
        self.conn.commit()
    
    def reduce_trust(self, invoker, trustee, amount, currency):
        trustor = self.current_account(invoker)
        self.cur.execute("""SELECT amount FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
        row = self.cur.fetchone()
        if row:
            if row[0] > amount:
                self.conn.commit()
                self.cur.execute("""UPDATE trusts SET amount = amount - %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
                self.cur.execute("""INSERT INTO trust_changes (trustor, trustee, changed_by, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
                self.conn.commit()
                self.send_pm(invoker, "Reduced trust in %s by %f" % (trustee, amount))
            else:
                self.cur.execute("""INSERT INTO trust_changes (trustor, trustee, changed_by, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, -row[0], currency))
                self.cur.execute("""DELETE FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
                self.conn.commit()
                self.send_pm(invoker, "Revoked trust in %s" % (trustee))
    
    def send_payment(self, invoker, recipient, amount, currency):
        account = self.current_account(invoker)
        paths = self.find_paths(account, recipient, amount, currency)
        total_amount = 0
        for pair in paths:
            total_amount += pair[1]
        if total_amount == amount:
            self.transact_paths(invoker, account, recipient, amount, paths, currency)
            self.send_pm(invoker, "Sent %0.2f%s to %s" % (amount, currency, recipient))
            # Send receipts to logged-in managers
            for manager in self.group_managers(recipient):
                if manager == recipient:
                    self.send_pm(manager, "%s sent you %0.2f%s" % (account, amount, currency))
                else:
                    self.send_pm(manager, "%s sent %s %0.2f%s" % (account, recipient, amount, currency))
        else:
            self.send_pm(invoker, "Could not send payment of %0.2f%s to %s, maximum is %0.2f%s" % (amount, currency, recipient, total_amount, currency))
    
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
    
    def transact_paths(self, invoker, sender, recipient, amount, paths, currency):
        # Log record
        self.cur.execute("""INSERT INTO transactions (sent_from, sent_to, amount, currency, invoker) VALUES (%s, %s, %s, %s, %s) RETURNING transaction_id""", (sender, recipient, amount, currency, invoker))
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
