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
            msg = packet.data['text'].lower()
            msg = re.sub('\xa7.', '', msg)
            match = re.search('^([A-Za-z0-9]+) whispers ([A-Za-z0-9]+)(.*)', msg)
            if match:
                sender = match.group(1)
                command = match.group(2)
                remaining = match.group(3)
                if command == 'trust':
                    arg_match = re.search('^ ([A-Za-z0-9]+) ([0-9]+(?:\.[0-9]{1,2})?)d', remaining)
                    if arg_match:
                        self.send_pm(sender, "Matched trust arguments")
                        self.add_trust(sender, arg_match.group(1), Decimal(arg_match.group(2)), 'd')
                    else:
                        self.send_pm(sender, "Usage: trust <person> <amount>d")
                elif command == 'pay':
                    arg_match = re.search('^ ([A-Za-z0-9]+) ([0-9]+(?:\.[0-9]{1,2})?)d', remaining)
                    if arg_match:
                        self.send_pm(sender, "Matched pay arguments")
                        self.send_payment(sender, arg_match.group(1), Decimal(arg_match.group(2)), 'd')
                    else:
                        self.send_pm(sender, "Usage: pay <person> <amount>d")
                elif command == 'payas':
                    arg_match = re.search('^ ([A-Za-z0-9]+) ([A-Za-z0-9]+) ([0-9]+(?:\.[0-9]{1,2})?)d', remaining)
                    if arg_match:
                        self.send_pm(sender, "Matched pay arguments")
                        self.send_payment(arg_match.group(1), arg_match.group(2), Decimal(arg_match.group(3)), 'd')
                    else:
                        self.send_pm(sender, "Usage: pay <person> <amount>d")
                else:
                    self.send_pm(sender, "Command not understood: %s" % (command))
        except Exception as error:
            print "Error handling command %s: %s" % (msg, error)
            print traceback.format_exc()
    
    def send_pm(self, user, message):
        self.client.push(Packet(ident=0x03, data={'text':"/msg %s %s" % (user, message)}))
    
    def add_trust(self, trustor, trustee, amount, currency):
        self.cur.execute("""SELECT 1 FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
        row = self.cur.fetchone()
        if row:
            self.cur.execute("""UPDATE trusts SET amount = amount + %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
        else:
            self.cur.execute("""INSERT INTO trusts (trustor, trustee, amount, currency) VALUES (%s, %s, %s, %s)""", (trustor, trustee, amount, currency))
        self.conn.commit()
    
    def reduce_trust(self, trustor, trustee, amount, currency):
        self.cur.execute("""SELECT amount FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (currency, expand_set))
        row = self.cur.fetchone()
        if row:
            if row[0] >= amount:
                self.conn.commit()
                self.cur.execute("""UPDATE trusts SET amount = amount - %s WHERE trustor = %s AND trustee = %s AND currency = %s""", (amount, trustor, trustee, currency))
                self.send_pm(sender, "Reduced trust in %s by %f" % (recipient, amount))
            else:
                self.delete_trust(trustor, trustee, currency)
        else:
            self.delete_trust(trustor, trustee, currency)
    
    def delete_trust(self, trustor, trustee, currency):
        self.cur.execute("""DELETE FROM trusts WHERE trustor = %s AND trustee = %s AND currency = %s""", (trustor, trustee, currency))
        self.conn.commit()
        self.send_pm(sender, "Revoked trust in %s" % (recipient))
    
    def send_payment(self, sender, recipient, amount, currency):
        paths = self.find_paths(sender, recipient, amount, currency)
        total_amount = 0
        for pair in paths:
            total_amount += pair[1]
        if total_amount == amount:
            self.transact_paths(paths, currency)
            self.send_pm(sender, "Sent %0.2f to %s" % (amount, recipient))
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
            self.cur.execute("""SELECT debt_from, debt_to FROM debts WHERE currency = %s AND debt_to IN (%s)""", (currency, tuple(expand_set)))
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
        # TODO: find how much we can send along a path
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
    
    def transact_paths(self, paths, currency):
        for pair in paths:
            print pair
            path = pair[0]
            amount = pair[1]
            from_account = path[0]
            for to_account in path[1:]:
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
