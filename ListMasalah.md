Kemungkinan (belum di cek):
- Record ID ada yang sama
- Kemungkinan data double yang sudah terfilter by name tapi memiliki informasi yang berbeda pada kolom lain seperti halnya email, company dsb yang mana cukup krusial jika ternyata data lainnya terdapat salah satu yang benar tetapi terhapus


Fix error:
- Full Name (Banyak yang redundant dimana merupakan data dari first_name yang disingkat dan last_name juga first name yang digabung sama last name jadi nama panjang) untuk yang bagian ini saya ingin melakukan pengecekan juga terhadap kemungkinan kemiripan nama yang menggunakan format lain, jika kemiripan nama melebihi 80% maka akan saya remove menjadi double name dengan catatan human in the loop
- Ketidak konsistenan dalam format waktunya dan juga format penulisan untuk kolom lainnya, akan saya sesuaikan dengan standar yang ada pada CRM
