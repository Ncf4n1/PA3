'''
Created on Oct 12, 2016
@author: mwittie
'''
import queue
import threading


## wrapper class for a queue of packets
class Interface:
    ## @param maxsize - the maximum size of the queue storing packets
    def __init__(self, maxsize=0):
        self.queue = queue.Queue(maxsize);
        self.mtu = None

    ##get packet from the queue interface
    def get(self):
        try:
            return self.queue.get(False)
        except queue.Empty:
            return None

    ##put the packet into the interface queue
    # @param pkt - Packet to be inserted into the queue
    # @param block - if True, block until room in queue, if False may throw queue.Full exception
    def put(self, pkt, block=False):
        self.queue.put(pkt, block)


## Implements a network layer packet (different from the RDT packet
# from programming assignment 2).
# NOTE: This class will need to be extended to for the packet to include
# the fields necessary for the completion of this assignment.
class NetworkPacket:
    ## packet encoding lengths
    dst_addr_S_length = 5
    offset_length = 3

    ##@param dst_addr: address of the destination host
    # @param data_S: packet payload
    def __init__(self, dst_addr, data_S, frag_flag, offset):
        self.dst_addr = dst_addr
        self.data_S = data_S
        self.frag_flag = frag_flag
        self.offset = offset

    ## called when printing the object
    def __str__(self):
        return self.to_byte_S()

    ## convert packet to a byte string for transmission over links
    def to_byte_S(self):
        byte_S = str(self.dst_addr).zfill(self.dst_addr_S_length)
        byte_S += str(self.frag_flag)
        byte_S += str(self.offset).zfill(self.offset_length)
        byte_S += self.data_S
        return byte_S

    ## extract a packet object from a byte string
    # @param byte_S: byte string representation of the packet
    @classmethod
    def from_byte_S(self, byte_S):
        dst_addr = int(byte_S[0 : NetworkPacket.dst_addr_S_length])
        frag_flag = int(byte_S[NetworkPacket.dst_addr_S_length : NetworkPacket.dst_addr_S_length + 1])
        offset = int(byte_S[NetworkPacket.dst_addr_S_length + 1 : NetworkPacket.dst_addr_S_length + 1 + self.offset_length])
        data_S = byte_S[NetworkPacket.dst_addr_S_length + 1 + self.offset_length : ]
        return self(dst_addr, data_S, frag_flag, offset)




## Implements a network host for receiving and transmitting data
class Host:
    packet_reassembly_list = []
    ##@param addr: address of this node represented as an integer
    def __init__(self, addr):
        self.addr = addr
        self.in_intf_L = [Interface()]
        self.out_intf_L = [Interface()]
        self.stop = False #for thread termination

    ## called when printing the object
    def __str__(self):
        return 'Host_%s' % (self.addr)

    ## create a packet and enqueue for transmission
    # @param dst_addr: destination address for the packet
    # @param data_S: data being transmitted to the network layer
    def udt_send(self, dst_addr, data_S):
        packet_offset = 0
        while len(data_S) + NetworkPacket.dst_addr_S_length + NetworkPacket.offset_length + 1 > self.out_intf_L[0].mtu:
            new_data_S = data_S[0:self.out_intf_L[0].mtu - NetworkPacket.dst_addr_S_length - NetworkPacket.offset_length - 1]
            p = NetworkPacket(dst_addr, new_data_S, 1, packet_offset)
            self.out_intf_L[0].put(p.to_byte_S()) #send packets always enqueued successfully
            print('%s: sending packet "%s" on the out interface with mtu=%d' % (self, p, self.out_intf_L[0].mtu))
            data_S = data_S[self.out_intf_L[0].mtu - NetworkPacket.dst_addr_S_length - NetworkPacket.offset_length - 1:]
            packet_offset += self.out_intf_L[0].mtu
        last_p = NetworkPacket(dst_addr, data_S, 0, packet_offset)
        self.out_intf_L[0].put(last_p.to_byte_S())
        print('%s: sending final packet "%s" on the out interface with mtu=%d' % (self, last_p, self.out_intf_L[0].mtu))

    ## receive packet from the network layer
    def udt_receive(self):
        pkt_S = self.in_intf_L[0].get()
        if pkt_S is not None:
            print('%s: received packet "%s" on the in interface' % (self, pkt_S))
            self.packet_reassembly_list.append(pkt_S)
            if (pkt_S[NetworkPacket.dst_addr_S_length] == '0'):
                final_packet_string = ''
                min_offset = float("inf")
                test_min_offset = ''
                while True:
                    current_lowest_packet = self.packet_reassembly_list[0]
                    for packet in self.packet_reassembly_list:
                        test_min_offset = packet[NetworkPacket.dst_addr_S_length + 1:NetworkPacket.dst_addr_S_length + 3]
                        if int(test_min_offset) < min_offset:
                            current_lowest_packet = packet
                            min_offset = int(test_min_offset)

                    final_packet_string += current_lowest_packet[NetworkPacket.dst_addr_S_length + NetworkPacket.offset_length + 1:]
                    self.packet_reassembly_list.remove(current_lowest_packet)

                    if (len(self.packet_reassembly_list) == 0):
                        break

                print('Packet reassembled at %s with message %s' % (self, final_packet_string))


    ## thread target for the host to keep receiving data
    def run(self):
        print (threading.currentThread().getName() + ': Starting')
        while True:
            #receive data arriving to the in interface
            self.udt_receive()
            #terminate
            if(self.stop):
                print (threading.currentThread().getName() + ': Ending')
                return



## Implements a multi-interface router described in class
class Router:

    ##@param name: friendly router name for debugging
    # @param intf_count: the number of input and output interfaces
    # @param max_queue_size: max queue length (passed to Interface)
    def __init__(self, name, intf_count, max_queue_size, routing_table):
        self.stop = False #for thread termination
        self.name = name
        #create a list of interfaces
        self.in_intf_L = [Interface(max_queue_size) for _ in range(intf_count)]
        self.out_intf_L = [Interface(max_queue_size) for _ in range(intf_count)]

        self.routing_table = routing_table

    ## called when printing the object
    def __str__(self):
        return 'Router_%s' % (self.name)

    ## look through the content of incoming interfaces and forward to
    # appropriate outgoing interfaces
    def forward(self):
        for i in range(len(self.in_intf_L)):
            pkt_S = None
            try:
                #get packet from interface i
                pkt_S = self.in_intf_L[i].get()
                #if packet exists make a forwarding decision
                if pkt_S is not None:
                    packet_offset = 0
                    p = NetworkPacket.from_byte_S(pkt_S) #parse a packet out
                    while len(p.data_S) + NetworkPacket.dst_addr_S_length + NetworkPacket.offset_length + 1 > self.out_intf_L[i].mtu:
                        new_data_S = p.data_S[0:self.out_intf_L[i].mtu - NetworkPacket.dst_addr_S_length - NetworkPacket.offset_length - 1]
                        packet = NetworkPacket(p.dst_addr, new_data_S, 1, packet_offset)
                        self.out_intf_L[i].put(packet.to_byte_S(), True) #send packets always enqueued successfully
                        print('%s: forwarding packet "%s" from interface %d to %d with mtu %d' \
                            % (self, p, i, i, self.out_intf_L[i].mtu))
                        p.data_S = p.data_S[self.out_intf_L[i].mtu - NetworkPacket.dst_addr_S_length - NetworkPacket.offset_length - 1:]
                        packet_offset += self.out_intf_L[i].mtu
                    last_p = NetworkPacket(p.dst_addr, p.data_S, p.frag_flag, packet_offset)
                    self.out_intf_L[i].put(last_p.to_byte_S(), True)
                    # HERE you will need to implement a lookup into the
                    # forwarding table to find the appropriate outgoing interface
                    # for now we assume the outgoing interface is also i
                    print('%s: forwarding final packet "%s" from interface %d to %d with mtu %d' \
                        % (self, p, i, i, self.out_intf_L[i].mtu))
            except queue.Full:
                print('%s: packet "%s" lost on interface %d' % (self, p, i))
                pass

    ## thread target for the host to keep forwarding data
    def run(self):
        print (threading.currentThread().getName() + ': Starting')
        while True:
            self.forward()
            if self.stop:
                print (threading.currentThread().getName() + ': Ending')
                return
